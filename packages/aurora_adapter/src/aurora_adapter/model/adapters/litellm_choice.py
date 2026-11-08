"""复用 LiteLLM 决策转换与传输，独立持有连接池，不修改 SDK 全局配置。"""

import httpx
from litellm.decisions.call import SystemOneRequestFields, prepare_call
from litellm.llms.custom_httpx.http_handler import AsyncHTTPHandler
from litellm.llms.custom_httpx.llm_http_handler import BaseLLMHTTPHandler
from litellm.types.decisions import ChoiceQuestion, DecisionsIRChoiceAnswer, UnsupportedDecisionsRequest

from ..decisions import ChoiceRequest
from ..models import ModelConfig
from ..protocols import ModelError, ModelProtocolError


class LiteLLMChoiceClient:
    """单题文本选择；在固定 SDK 版本的底层入口注入实例传输，禁用共享客户端和自动重试。"""

    def __init__(
        self, config: ModelConfig, *, api_key: str | None, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        if config.capabilities is not None:
            raise ValueError("choice 不接受聊天模型的 capabilities 配置")
        if config.base_url is not None:
            base = httpx.URL(config.base_url)
            if base.scheme not in ("http", "https") or not base.host or base.query or base.fragment or base.userinfo:
                raise ValueError("决策 base_url 必须为不含凭证、查询或片段的 HTTP(S) 地址")
        self._config, self._api_key = config, api_key
        self._transport = AsyncHTTPHandler(transport=transport, follow_redirects=False)
        self._handler = BaseLLMHTTPHandler()
        self._active = self._closed = False

    async def choose(self, request: ChoiceRequest) -> str:
        if self._closed or self._active:
            raise ModelError("决策客户端已关闭或仍有在途判断")
        self._active = True
        try:
            call = prepare_call(
                model=self._config.model,
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
                api_base=self._config.base_url,
                timeout=30.0,
                custom_llm_provider=self._config.provider,
                extra_headers=None,
                kwargs={"num_retries": 0, "max_retries": 0, "caching": False},
            )
            body = call.provider_config.transform_decisions_request(
                call.model, call.ir_request, call.custom_llm_provider
            )
            if isinstance(body, UnsupportedDecisionsRequest):
                raise ModelProtocolError("决策供应商不支持当前请求")
            response = await self._handler.adecisions(
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
            if len(response.answers) != 1:
                raise ModelProtocolError("决策响应必须包含唯一答案")
            answer = response.answers[0]
            if (
                not isinstance(answer, DecisionsIRChoiceAnswer)
                or type(answer.choice) is not str
                or answer.choice not in request["criteria"]
            ):
                raise ModelProtocolError("决策模型未返回已声明的 choice")
            return answer.choice
        except ModelError:
            raise
        except Exception as error:  # noqa: BLE001 - SDK 错误正文可能包含凭证和业务材料。
            raise ModelError(f"决策供应商调用失败：{type(error).__name__}") from None
        finally:
            self._active = False

    async def aclose(self) -> None:
        if self._closed:
            return
        if self._active:
            raise ModelError("关闭决策客户端前必须结束在途判断")
        await self._transport.close()
        self._api_key = None
        self._closed = True
