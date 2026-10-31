"""LiteLLM 文本与工具边界；SDK 对象仅在本模块内部使用。"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from copy import deepcopy
from typing import Any, cast

from aurora_core.json_data import decode_json, encode_json
from litellm.utils import supports_native_streaming

from ..models import (
    FinishReason,
    JsonValue,
    ModelCapabilities,
    ModelChunk,
    ModelConfig,
    ModelRequest,
    ModelResponse,
    ToolCall,
)
from ..protocols import ModelError, ModelProtocolError, ResponseBuffer, UnsupportedCapability, require_capabilities


def _object(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        value = value.model_dump()
    if not isinstance(value, dict):
        raise ModelProtocolError("模型响应必须为对象")
    return value


def _choice(value: Any, *, streaming: bool) -> dict[str, Any] | None:
    choices = _object(value).get("choices")
    if streaming and choices == []:
        return None
    if not isinstance(choices, list) or len(choices) != 1:
        raise ModelProtocolError("模型响应必须包含唯一 choice")
    choice = _object(choices[0])
    if choice.get("index", 0) != 0:
        raise ModelProtocolError("模型响应 choice 的 index 必须为 0")
    return choice


def _text(value: Any) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ModelProtocolError("模型文本与工具增量必须为字符串")
    return value


def _reason(value: Any) -> FinishReason:
    if value not in ("stop", "tool_calls", "length", "content_filter"):
        raise ModelProtocolError("模型结束原因不受支持或缺失")
    return cast(FinishReason, value)


def _tool(value: dict[str, Any]) -> ToolCall:
    if value.get("type", "function") != "function":
        raise ModelProtocolError("仅支持 function 工具调用")
    function = _object(value.get("function"))
    call_id, name = value.get("id"), function.get("name")
    if not isinstance(call_id, str) or not call_id or not isinstance(name, str) or not name:
        raise ModelProtocolError("工具调用必须具有完整 id 与名称")
    arguments = function.get("arguments")
    if not isinstance(arguments, str):
        raise ModelProtocolError("工具参数必须为完整 JSON 字符串")
    try:
        decoded = decode_json(arguments)
    except (ValueError, TypeError, RecursionError):
        raise ModelProtocolError("工具参数不是有效的严格 JSON 对象") from None
    if not isinstance(decoded, dict):
        raise ModelProtocolError("工具参数必须为 JSON 对象")
    return {"id": call_id, "name": name, "arguments": cast(dict[str, JsonValue], decoded)}


def _calls(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ModelProtocolError("tool_calls 必须为列表")
    return [_object(item) for item in value]


def _payload(request: ModelRequest) -> dict[str, Any]:
    messages: list[dict[str, Any]] = []
    for message in deepcopy(request["messages"]):
        converted: dict[str, Any] = dict(message)
        if "tool_calls" in message:
            converted["tool_calls"] = [
                {
                    "id": call["id"],
                    "type": "function",
                    "function": {"name": call["name"], "arguments": encode_json(call["arguments"])},
                }
                for call in message["tool_calls"]
            ]
        messages.append(converted)
    payload: dict[str, Any] = {"messages": messages}
    if request.get("tools"):
        payload["tools"] = [{"type": "function", "function": deepcopy(tool)} for tool in request["tools"]]
    return payload


class LiteLLMClient:
    """串行调用的独立实例，支持 OpenAI 兼容接口和 Anthropic。

    能力来自 LiteLLM 模型目录，未声明的能力明确拒绝。每次流在 async with
    退出时关闭；宿主结束全部调用后关闭实例。SDK 重试与响应缓存均不启用。
    """

    def __init__(self, sdk: Any, transport: Any, config: ModelConfig, api_key: str | None) -> None:
        self._sdk = sdk
        self._transport = transport
        self._config = config
        self._api_key = api_key
        self._active = False
        self._closed = False
        self.capabilities = ModelCapabilities(
            streaming=supports_native_streaming(config.model, custom_llm_provider=None),
            tool_calls=sdk.supports_function_calling(config.model),
        )

    def _begin(self, request: ModelRequest, *, streaming: bool) -> None:
        if self._closed:
            raise ModelError("模型客户端已关闭")
        if self._active:
            raise ModelError("同一模型客户端不支持并发调用")
        require_capabilities(self, request, streaming=streaming)
        self._active = True

    def _error(self, error: Exception) -> Exception:
        if isinstance(error, (ModelError, TimeoutError)):
            return error
        if isinstance(error, self._sdk.Timeout):
            return TimeoutError("模型供应商请求超时")
        return ModelError(f"模型供应商调用失败：{type(error).__name__}")

    async def _request(self, request: ModelRequest, *, streaming: bool) -> Any:
        payload = _payload(request)
        try:
            return await self._sdk.acompletion(
                model=self._config.model,
                api_base=self._config.base_url,
                api_key=self._api_key,
                client=self._transport,
                stream=streaming,
                num_retries=0,
                max_retries=0,
                caching=False,
                **payload,
            )
        except Exception as error:  # noqa: BLE001 - SDK 异常在适配层统一转换，不上泄供应商对象。
            raise self._error(error) from None

    async def complete(self, request: ModelRequest) -> ModelResponse:
        self._begin(request, streaming=False)
        try:
            choice = _choice(await self._request(request, streaming=False), streaming=False)
            assert choice is not None
            message = _object(choice.get("message"))
            if message.get("function_call"):
                raise ModelProtocolError("不支持旧式 function_call 响应")
            buffer = ResponseBuffer()
            buffer.append({"type": "text", "text": _text(message.get("content"))})
            for call in _calls(message.get("tool_calls")):
                buffer.append({"type": "tool_call", "tool_call": _tool(call)})
            buffer.append({"type": "finish", "reason": _reason(choice.get("finish_reason"))})
            return buffer.result()
        finally:
            self._active = False

    async def _chunks(self, response: Any) -> AsyncIterator[ModelChunk]:
        pending: dict[int, dict[str, Any]] = {}
        reason: FinishReason | None = None
        iterator = aiter(response)
        while True:
            try:
                value = await anext(iterator)
            except StopAsyncIteration:
                break
            except Exception as error:  # noqa: BLE001 - SDK 异常在适配层统一转换，不上泄供应商对象。
                raise self._error(error) from None
            choice = _choice(value, streaming=True)
            if choice is None:
                continue
            delta = _object(choice.get("delta"))
            text = _text(delta.get("content"))
            if (
                not text
                and not delta.get("tool_calls")
                and not delta.get("function_call")
                and choice.get("finish_reason") is None
            ):
                continue
            if reason is not None:
                raise ModelProtocolError("结束片段之后不得再输出内容")
            if delta.get("function_call"):
                raise ModelProtocolError("不支持旧式 function_call 响应")
            if text:
                yield {"type": "text", "text": text}
            for part in _calls(delta.get("tool_calls")):
                index = part.get("index")
                if type(index) is not int or index < 0:
                    raise ModelProtocolError("工具增量必须提供非负整数 index")
                if part.get("type") not in (None, "function"):
                    raise ModelProtocolError("仅支持 function 工具调用")
                call = pending.setdefault(index, {"id": "", "function": {"name": "", "arguments": ""}})
                call["id"] += _text(part.get("id"))
                function = _object(part.get("function") or {})
                for field in ("name", "arguments"):
                    call["function"][field] += _text(function.get(field))
            if choice.get("finish_reason") is not None:
                reason = _reason(choice["finish_reason"])
        if reason is None:
            raise ModelProtocolError("响应流缺少结束片段")
        buffer = ResponseBuffer()
        for index in sorted(pending):
            chunk: ModelChunk = {"type": "tool_call", "tool_call": _tool(pending[index])}
            buffer.append(chunk)
        buffer.append({"type": "finish", "reason": reason})
        result = buffer.result()
        for call in result["tool_calls"]:
            yield {"type": "tool_call", "tool_call": call}
        yield {"type": "finish", "reason": reason}

    @asynccontextmanager
    async def stream(self, request: ModelRequest) -> AsyncIterator[AsyncIterator[ModelChunk]]:
        self._begin(request, streaming=True)
        try:
            response = await self._request(request, streaming=True)
            chunks = self._chunks(response)
            try:
                yield chunks
            finally:
                await chunks.aclose()
                try:
                    await response.aclose()
                except Exception as error:  # noqa: BLE001 - SDK 异常在适配层统一转换，不上泄供应商对象。
                    raise self._error(error) from None
        finally:
            self._active = False

    async def aclose(self) -> None:
        if self._closed:
            return
        if self._active:
            raise ModelError("关闭客户端前必须结束在途调用")
        try:
            await self._transport.close()
        except Exception as error:  # noqa: BLE001 - SDK 异常在适配层统一转换，不上泄供应商对象。
            raise self._error(error) from None
        self._closed = True
        self._api_key = None


async def create(config: ModelConfig, *, api_key: str | None = None) -> LiteLLMClient:
    """创建自有连接池；不修改 LiteLLM 的全局客户端、密钥或回调配置。"""
    import litellm
    from litellm.llms.custom_httpx.http_handler import AsyncHTTPHandler
    from openai import AsyncOpenAI

    try:
        _, provider, _, _ = litellm.get_llm_provider(model=config.model)
        if provider == "openai":
            transport = AsyncOpenAI(api_key=api_key, base_url=config.base_url, max_retries=0)
        elif provider == "anthropic":
            transport = AsyncHTTPHandler()
        else:
            raise UnsupportedCapability("当前 LiteLLM 工厂仅支持 openai/ 与 anthropic/ 模型")
    except ModelError:
        raise
    except Exception as error:  # noqa: BLE001 - SDK 异常在适配层统一转换，不上泄供应商对象。
        raise ModelError(f"模型客户端初始化失败：{type(error).__name__}") from None
    try:
        return LiteLLMClient(litellm, transport, config, api_key)
    except BaseException as error:
        await transport.close()
        if isinstance(error, Exception) and not isinstance(error, ModelError):
            raise ModelError(f"模型能力解析失败：{type(error).__name__}") from None
        raise
