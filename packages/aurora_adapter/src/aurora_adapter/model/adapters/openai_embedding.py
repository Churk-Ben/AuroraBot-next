"""OpenAI 兼容文本向量传输；独占连接池，不重试或跟随重定向。"""

import httpx

from ..embeddings import normalize_vectors
from ..models import ModelConfig
from ..protocols import ModelError, ModelProtocolError


class OpenAIEmbeddingClient:
    def __init__(
        self, config: ModelConfig, *, api_key: str | None, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        if config.provider not in (None, "openai"):
            raise ValueError("向量适配器只支持 provider=openai 的兼容端点")
        if config.capabilities is not None or config.thinking is not None or config.reasoning_effort is not None:
            raise ValueError("向量模型不接受聊天能力或思考配置")
        base = httpx.URL(config.base_url or "https://api.openai.com/v1")
        if base.scheme not in ("http", "https") or not base.host or base.query or base.fragment or base.userinfo:
            raise ValueError("向量 base_url 必须为不含凭证、查询或片段的 HTTP(S) 地址")
        self._model = config.model
        self._client = httpx.AsyncClient(
            base_url=str(base).rstrip("/") + "/",
            headers={} if api_key is None else {"Authorization": f"Bearer {api_key}"},
            transport=transport,
            timeout=30,
            follow_redirects=False,
        )
        self._active = False

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if self._client.is_closed or self._active:
            raise ModelError("向量客户端已关闭或仍有在途请求")
        if not texts or any(not isinstance(text, str) or not text.strip() for text in texts):
            raise ValueError("向量输入必须为非空文本列表")
        self._active = True
        try:
            response = await self._client.post(
                "embeddings", json={"model": self._model, "input": texts, "encoding_format": "float"}
            )
            response.raise_for_status()
            data = response.json().get("data")
            if not isinstance(data, list) or len(data) != len(texts):
                raise ModelProtocolError("向量响应数量与输入不一致")
            by_index = {}
            for item in data:
                if not isinstance(item, dict) or type(item.get("index")) is not int or item["index"] in by_index:
                    raise ModelProtocolError("向量响应索引无效或重复")
                by_index[item["index"]] = item.get("embedding")
            if set(by_index) != set(range(len(texts))):
                raise ModelProtocolError("向量响应索引与输入不一致")
            return normalize_vectors([by_index[i] for i in range(len(texts))], len(texts))
        except ModelError:
            raise
        except Exception as error:  # noqa: BLE001 - 传输正文可能包含凭证和记忆内容。
            raise ModelError(f"向量供应商调用失败：{type(error).__name__}") from None
        finally:
            self._active = False

    async def aclose(self) -> None:
        if self._active:
            raise ModelError("关闭向量客户端前必须结束在途请求")
        await self._client.aclose()
        self._client.headers.pop("Authorization", None)
