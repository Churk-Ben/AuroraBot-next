"""类型化选择模型契约；不生成文本或执行工具。"""

from typing import Protocol, TypedDict

from .models import JsonValue, ModelConfig


class ChoiceRequest(TypedDict):
    state: JsonValue
    instructions: str
    criteria: dict[str, str]


class ChoiceClient(Protocol):
    async def choose(self, request: ChoiceRequest) -> str:
        """返回 criteria 中的一个键；错误与取消不得伪装为选择。"""
        ...

    async def aclose(self) -> None:
        """关闭自有连接；调用方须先结束在途判断。"""
        ...


class ChoiceFactory(Protocol):
    async def __call__(self, config: ModelConfig, *, api_key: str | None) -> ChoiceClient: ...


async def create_jev(config: ModelConfig, *, api_key: str | None) -> ChoiceClient:
    """仅实例化时导入 Jev 的可选 HTTP 依赖。"""
    from .adapters.jev import JevChoiceClient

    return JevChoiceClient(config, api_key=api_key)
