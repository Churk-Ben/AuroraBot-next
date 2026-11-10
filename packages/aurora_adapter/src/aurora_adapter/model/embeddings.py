"""文本向量契约；供应商客户端和凭证只在运行期创建。"""

import math
from typing import Protocol

from .models import ModelConfig
from .protocols import ModelProtocolError


class EmbeddingClient(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """按输入顺序返回等维、有限且非零的向量。"""
        ...

    async def aclose(self) -> None: ...


class EmbeddingFactory(Protocol):
    async def __call__(self, config: ModelConfig, *, api_key: str | None) -> EmbeddingClient: ...


def normalize_vectors(value: object, count: int) -> list[list[float]]:
    """校验批次数、维数及数值，并归一化为用于余弦检索的单位向量。"""
    if not isinstance(value, list) or len(value) != count:
        raise ModelProtocolError("向量响应数量与输入不一致")
    result = []
    dimension = None
    for vector in value:
        if not isinstance(vector, list) or not vector or (dimension is not None and len(vector) != dimension):
            raise ModelProtocolError("向量必须非空且维数一致")
        if any(type(v) not in (int, float) or not math.isfinite(v) for v in vector):
            raise ModelProtocolError("向量包含无效数值")
        norm = math.hypot(*vector)
        if not norm or not math.isfinite(norm):
            raise ModelProtocolError("向量范数必须有限且大于零")
        dimension = len(vector)
        result.append([v / norm for v in vector])
    return result


async def create_openai_embedding(config: ModelConfig, *, api_key: str | None) -> EmbeddingClient:
    """仅创建实例时加载 HTTP 依赖；支持 OpenAI 兼容 embeddings 端点。"""
    from .adapters.openai_embedding import OpenAIEmbeddingClient

    return OpenAIEmbeddingClient(config, api_key=api_key)
