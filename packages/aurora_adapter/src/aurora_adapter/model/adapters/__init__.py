"""真实模型工厂；仅在创建实例时加载供应商 SDK。"""

from ..models import ModelConfig
from ..protocols import ModelClient


async def create_litellm(config: ModelConfig, *, api_key: str | None = None) -> ModelClient:
    """创建独立的 LiteLLM 客户端，不在插件发现阶段初始化网络资源。"""
    from .litellm import create

    return await create(config, api_key=api_key)
