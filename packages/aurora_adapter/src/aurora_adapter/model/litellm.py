"""LiteLLM 聊天、决策与向量客户端；实例独占传输，不修改 SDK 全局配置。"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, contextmanager
from copy import deepcopy
from typing import Any

import httpx
import litellm
from litellm.decisions.call import SystemOneRequestFields, prepare_call
from litellm.litellm_core_utils.streaming_chunk_builder_utils import ChunkProcessor
from litellm.llms.custom_httpx.http_handler import AsyncHTTPHandler
from litellm.llms.custom_httpx.llm_http_handler import BaseLLMHTTPHandler
from litellm.llms.openai_like.json_loader import JSONProviderRegistry
from litellm.types.decisions import ChoiceQuestion, DecisionsIRChoiceAnswer, UnsupportedDecisionsRequest
from litellm.utils import supports_native_streaming
from openai import AsyncOpenAI

from ._codec import (
    chat_payload,
    chat_response,
    choice_data,
    finish_reason,
    object_data,
    text_data,
    thinking_blocks,
    tool_parts,
)
from .content import require_capabilities
from .contract import (
    ChatCapabilities,
    ChatChunk,
    ChatRequest,
    ChatResponse,
    ChoiceRequest,
    ModelConfig,
    ModelError,
    ModelKind,
    ModelProtocolError,
    UnsupportedCapability,
)
from .response import normalize_vectors
from .usage import UsageRecord


class _UsageStream(httpx.AsyncByteStream):
    """原样交付响应字节，只提取原始 SSE 中的用量。"""

    def __init__(self, stream: httpx.AsyncByteStream, usage: UsageRecord) -> None:
        self.stream, self.usage = stream, usage

    async def __aiter__(self):
        async for chunk in self.stream:
            self.usage.feed(chunk)
            yield chunk

    async def aclose(self) -> None:
        await self.stream.aclose()


@contextmanager
def _errors():
    try:
        yield
    except (ModelError, TimeoutError):
        raise
    except litellm.Timeout:
        raise TimeoutError("模型供应商请求超时") from None
    except Exception as error:  # noqa: BLE001 - SDK 错误可能携带凭证和完整输入。
        raise ModelError(f"模型供应商调用失败：{type(error).__name__}") from None


class _OpenAIWithoutRetries(AsyncOpenAI):
    """保持实例的零重试策略，避免 SDK embedding 分支把 0 改成默认预算。"""

    @property
    def max_retries(self) -> int:
        return 0

    @max_retries.setter
    def max_retries(self, value: int) -> None:
        pass


class LiteLLMClient:
    """按用途创建独立客户端；转换、供应商路由与向量请求由固定版本 SDK 提供。"""

    def __init__(
        self,
        config: ModelConfig,
        *,
        kind: ModelKind = "chat",
        api_key: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if kind != "chat" and (
            config.capabilities is not None or config.thinking is not None or config.reasoning_effort is not None
        ):
            raise ValueError("非聊天模型不接受聊天能力或思考配置")
        if config.base_url is not None:
            base = httpx.URL(config.base_url)
            if base.scheme not in ("http", "https") or not base.host or base.query or base.fragment or base.userinfo:
                raise ValueError("模型 base_url 必须为不含凭证、查询或片段的 HTTP(S) 地址")
        self.kind, self.config, self._api_key = kind, config, api_key
        self._active = self._closed = False
        self._usage: UsageRecord | None = None
        try:
            model, provider, _, base_url = litellm.get_llm_provider(
                model=config.model, custom_llm_provider=config.provider, api_base=config.base_url, api_key=api_key
            )
            self._model, self._provider, self._base_url = model, provider, base_url
            self.capabilities = config.capabilities or ChatCapabilities(
                streaming=kind == "chat" and supports_native_streaming(model, custom_llm_provider=provider),
                tool_calls=kind == "chat" and litellm.supports_function_calling(model, custom_llm_provider=provider),
            )
            openai_transport = (
                kind == "chat" and (provider in ("openai", "deepseek") or JSONProviderRegistry.exists(provider))
            ) or (
                kind == "embedding"
                and provider
                in (
                    "openai",
                    "together_ai",
                    "nvidia_nim",
                    "litellm_proxy",
                    "mistral",
                    "fireworks_ai",
                    "nebius",
                    "wandb",
                )
            )
            if openai_transport:
                if provider == "deepseek":
                    self._base_url = config.base_url or "https://api.deepseek.com"
                self._transport: Any = _OpenAIWithoutRetries(
                    api_key=api_key or "",
                    base_url=self._base_url,
                    max_retries=0,
                    http_client=httpx.AsyncClient(
                        transport=transport, follow_redirects=False, event_hooks={"response": [self._observe_usage]}
                    ),
                )
            elif (
                kind == "choice"
                or (kind == "chat" and provider == "anthropic")
                or (
                    kind == "embedding"
                    and provider in ("cohere", "cohere_chat", "voyage", "infinity", "openrouter", "sambanova")
                )
            ):
                self._transport = AsyncHTTPHandler(
                    transport=transport, follow_redirects=False, event_hooks={"response": [self._observe_usage]}
                )
            else:
                raise UnsupportedCapability("供应商尚未接入实例传输；兼容端点可配置 provider=openai 和 base_url")
        except ModelError:
            raise
        except Exception as error:  # noqa: BLE001 - 不上泄 SDK 凭证或供应商正文。
            raise ModelError(f"模型客户端初始化失败：{type(error).__name__}") from None

    async def _observe_usage(self, response: httpx.Response) -> None:
        if self._usage is None:
            return
        if "text/event-stream" in response.headers.get("content-type", ""):
            if response.is_stream_consumed:
                self._usage.feed(response.content)
            else:
                assert isinstance(response.stream, httpx.AsyncByteStream)
                response.stream = _UsageStream(response.stream, self._usage)
        else:
            await response.aread()
            try:
                self._usage.read(response.json())
            except ValueError:
                pass

    @asynccontextmanager
    async def _using(self, kind: ModelKind):
        if self._closed or self._active:
            raise ModelError("模型客户端已关闭或存在在途调用，不支持并发")
        if self.kind != kind:
            raise ModelError("模型调用用途与客户端不匹配")
        self._active = True
        self._usage = UsageRecord(kind, self.config.model)
        status = "incomplete"
        try:
            yield
            if self._usage.complete:
                status = "completed"
        except asyncio.CancelledError:
            status = "cancelled"
            raise
        except Exception:
            status = "failed"
            raise
        finally:
            self._usage.finish(status)
            self._usage = None
            self._active = False

    def _options(self) -> dict[str, Any]:
        return {
            "model": self._model,
            "custom_llm_provider": self._provider,
            "api_base": self._base_url,
            "api_key": self._api_key,
            "client": self._transport,
            "num_retries": 0,
            "max_retries": 0,
            "caching": False,
        }

    async def _chat(self, request: ChatRequest, *, streaming: bool):
        require_capabilities(self, request, streaming=streaming)
        options = self._options()
        payload = chat_payload(request)
        if self._provider == "deepseek":
            options["custom_llm_provider"] = "openai"
        if streaming and self._provider in ("openai", "deepseek"):
            payload["stream_options"] = {"include_usage": True}
        if self.config.thinking is not None:
            if self._provider == "anthropic":
                payload["thinking"] = deepcopy(self.config.thinking)
            else:
                payload["extra_body"] = {"thinking": deepcopy(self.config.thinking)}
        if self.config.reasoning_effort is not None:
            payload["reasoning_effort"] = self.config.reasoning_effort
        payload["allowed_openai_params"] = [name for name in ("tools", "reasoning_effort") if name in payload]
        with _errors():
            return await litellm.acompletion(**options, **payload, stream=streaming)

    async def complete(self, request: ChatRequest) -> ChatResponse:
        async with self._using("chat"):
            with _errors():
                result = chat_response(await self._chat(request, streaming=False))
                assert self._usage is not None
                self._usage.complete = True
                return result

    async def _chunks(self, response) -> AsyncIterator[ChatChunk]:
        with _errors():
            collected = []
            identities: dict[int, dict[str, Any]] = {}
            reason = None
            unsigned = False
            async for value in response:
                choice = choice_data(value, streaming=True)
                if choice is None:
                    continue
                delta = object_data(choice.get("delta"))
                text, reasoning = text_data(delta.get("content")), text_data(delta.get("reasoning_content"))
                blocks, calls = thinking_blocks(delta.get("thinking_blocks")), tool_parts(delta.get("tool_calls"))
                if not (
                    text or reasoning or blocks or calls or delta.get("function_call") or choice.get("finish_reason")
                ):
                    continue
                if reason is not None:
                    raise ModelProtocolError("结束片段之后不得再输出内容")
                if delta.get("function_call"):
                    raise ModelProtocolError("不支持旧式 function_call 响应")
                if text:
                    yield {"type": "text", "text": text}
                if reasoning:
                    yield {"type": "reasoning", "text": reasoning}
                for block in blocks:
                    if block["type"] == "redacted_thinking" and unsigned:
                        raise ModelProtocolError("思考块尚未获得签名")
                    unsigned = block["type"] == "thinking" and not block.get("signature")
                for call in calls:
                    index = call.get("index")
                    if type(index) is not int or index < 0 or call.get("type") not in (None, "function"):
                        raise ModelProtocolError("工具增量必须为 function 且具有非负整数 index")
                    identity = identities.setdefault(index, {"id": "", "name": "", "arguments": False})
                    function = object_data(call.get("function") or {})
                    identity["id"] += text_data(call.get("id"))
                    identity["name"] += text_data(function.get("name"))
                    identity["arguments"] |= bool(text_data(function.get("arguments")))
                    call.update(id=identity["id"], function={**function, "name": identity["name"]})
                if calls or blocks:
                    collected.append(
                        {"choices": [{"index": 0, "delta": {"tool_calls": calls, "thinking_blocks": blocks}}]}
                    )
                if choice.get("finish_reason") is not None:
                    reason = finish_reason(choice["finish_reason"])
            if reason is None or unsigned:
                raise ModelProtocolError("响应流缺少结束片段或思考回传签名")
            if any(not all(identity.values()) for identity in identities.values()):
                raise ModelProtocolError("工具调用必须具有完整身份与参数")
            message = {}
            if collected:
                processor = ChunkProcessor(collected)
                message = {
                    "tool_calls": processor.get_combined_tool_content(collected),
                    "thinking_blocks": processor.get_combined_thinking_content(collected),
                }
            result = chat_response({"choices": [{"message": message, "finish_reason": reason}]})
            for block in result.get("thinking_blocks", []):
                yield {"type": "thinking_block", "block": block}
            for call in result["tool_calls"]:
                yield {"type": "tool_call", "tool_call": call}
            assert self._usage is not None
            self._usage.complete = True
            yield {"type": "finish", "reason": reason}

    @asynccontextmanager
    async def stream(self, request: ChatRequest) -> AsyncIterator[AsyncIterator[ChatChunk]]:
        async with self._using("chat"):
            response = await self._chat(request, streaming=True)
            chunks = self._chunks(response)
            try:
                yield chunks
            finally:
                await chunks.aclose()
                with _errors():
                    await response.aclose()

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts or any(not isinstance(text, str) or not text.strip() for text in texts):
            raise ValueError("向量输入必须为非空文本列表")
        async with self._using("embedding"):
            with _errors():
                response = object_data(
                    await litellm.aembedding(**self._options(), input=texts, encoding_format="float")
                )
                data = response.get("data")
                if not isinstance(data, list) or len(data) != len(texts):
                    raise ModelProtocolError("向量响应数量与输入不一致")
                indices = [item.get("index") for item in data]
                if any(type(index) is not int for index in indices) or sorted(indices) != list(range(len(texts))):
                    raise ModelProtocolError("向量响应索引与输入不一致")
                result = normalize_vectors(
                    [item["embedding"] for item in sorted(data, key=lambda item: item["index"])], len(texts)
                )
                assert self._usage is not None
                self._usage.complete = True
                return result

    async def choose(self, request: ChoiceRequest) -> str:
        async with self._using("choice"):
            with _errors():
                call = prepare_call(
                    model=self.config.model,
                    fields=SystemOneRequestFields(
                        state=request["state"],
                        questions={
                            "decision": ChoiceQuestion(
                                type="choice", instructions=request["instructions"], criteria=request["criteria"]
                            )
                        },
                    ),
                    safety_identifier=None,
                    api_key=self._api_key,
                    api_base=self.config.base_url,
                    timeout=30.0,
                    custom_llm_provider=self.config.provider,
                    extra_headers=None,
                    kwargs={"num_retries": 0, "max_retries": 0, "caching": False},
                )
                body = call.provider_config.transform_decisions_request(
                    call.model, call.ir_request, call.custom_llm_provider
                )
                if isinstance(body, UnsupportedDecisionsRequest):
                    raise ModelProtocolError("决策供应商不支持当前请求")
                response = await BaseLLMHTTPHandler().adecisions(
                    model=call.model,
                    custom_llm_provider=call.custom_llm_provider,
                    logging_obj=None,
                    provider_config=call.provider_config,
                    request=call.ir_request,
                    body=body,
                    logged_body=body,
                    api_base=call.api_base,
                    api_key=call.api_key,
                    headers=call.headers,
                    timeout=call.timeout,
                    litellm_params=call.litellm_params,
                    client=self._transport,
                )
                if (
                    len(response.answers) != 1
                    or not isinstance(answer := response.answers[0], DecisionsIRChoiceAnswer)
                    or type(answer.choice) is not str
                    or answer.choice not in request["criteria"]
                ):
                    raise ModelProtocolError("决策模型必须返回唯一且已声明的 choice")
                assert self._usage is not None
                self._usage.complete = True
                return answer.choice

    async def aclose(self) -> None:
        if self._closed:
            return
        if self._active:
            raise ModelError("关闭模型客户端前必须结束在途调用")
        with _errors():
            await self._transport.close()
        self._api_key = None
        self._closed = True
