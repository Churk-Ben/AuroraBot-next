"""Jev SystemOne 的单题 choice 适配；凭证仅保留在运行期 HTTP 客户端。"""

import httpx2
from aurora_core.json_data import decode_json

from ..decisions import ChoiceRequest
from ..models import ModelConfig
from ..protocols import ModelError, ModelProtocolError


class JevChoiceClient:
    def __init__(
        self, config: ModelConfig, *, api_key: str | None, transport: httpx2.AsyncBaseTransport | None = None
    ) -> None:
        if not isinstance(api_key, str) or not api_key.strip():
            raise ValueError("Jev 需要运行期凭证")
        if config.provider is not None or config.capabilities is not None:
            raise ValueError("Jev choice 不接受聊天模型的 provider 或 capabilities 配置")
        base = httpx2.URL(config.base_url or "https://jevmodel.org")
        if base.scheme not in ("http", "https") or not base.host or base.query or base.fragment or base.userinfo:
            raise ValueError("Jev base_url 必须为不含凭证、查询或片段的 HTTP(S) 地址")
        self.model = config.model
        self._client = httpx2.AsyncClient(
            base_url=str(base).rstrip("/") + "/",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30,
            follow_redirects=False,
            transport=transport,
        )

    async def choose(self, request: ChoiceRequest) -> str:
        try:
            response = await self._client.post(
                "v1/systemone",
                json={
                    "model": self.model,
                    "state": request["state"],
                    "questions": {
                        "decision": {
                            "type": "choice",
                            "instructions": request["instructions"],
                            "criteria": request["criteria"],
                        }
                    },
                },
            )
        except httpx2.HTTPError:
            raise ModelError("Jev 决策传输失败") from None
        if response.status_code != 200:
            raise ModelError(f"Jev 决策失败，HTTP {response.status_code}")
        try:
            decoded = decode_json(response.text)
            if not isinstance(decoded, dict):
                raise TypeError
            answer = decoded["answers"]["decision"]
            choice = answer["choice"]
            if answer["type"] != "choice" or not isinstance(choice, str) or choice not in request["criteria"]:
                raise ValueError
        except (ValueError, TypeError, KeyError):
            raise ModelProtocolError("Jev 未返回有效的 choice 答案") from None
        return choice

    async def aclose(self) -> None:
        await self._client.aclose()
