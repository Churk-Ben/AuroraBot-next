"""可由 ctx 保存的模型数据；工具参数由适配器组装完整后交付。"""

from dataclasses import dataclass
from typing import Literal, NotRequired, TypedDict

type JsonValue = None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]
type FinishReason = Literal["stop", "tool_calls", "length", "content_filter"]


class ToolDefinition(TypedDict):
    """供模型选择的工具描述；parameters 使用 JSON Schema 对象。"""

    name: str
    description: str
    parameters: dict[str, JsonValue]


class ToolCall(TypedDict):
    """完整工具请求；id 用于关联后续工具消息，arguments 不含 JSON 碎片。"""

    id: str
    name: str
    arguments: dict[str, JsonValue]


class Message(TypedDict):
    """文本对话消息；assistant 可携带工具请求，tool 消息引用 tool_call_id。"""

    role: Literal["system", "user", "assistant", "tool"]
    content: str
    tool_calls: NotRequired[list[ToolCall]]
    tool_call_id: NotRequired[str]


class ModelRequest(TypedDict):
    """一次模型推理的输入；模型与连接选择由注入的客户端实例承担。"""

    messages: list[Message]
    tools: NotRequired[list[ToolDefinition]]


class ModelResponse(TypedDict):
    """一次推理结果；length/content_filter 结束不等于完整业务回答。"""

    text: str
    tool_calls: list[ToolCall]
    finish_reason: FinishReason


class TextDelta(TypedDict):
    type: Literal["text"]
    text: str


class ToolCallChunk(TypedDict):
    type: Literal["tool_call"]
    tool_call: ToolCall


class FinishChunk(TypedDict):
    """流的唯一最后片段；迭代结束但没有此片段表示响应不完整。"""

    type: Literal["finish"]
    reason: FinishReason


type ModelChunk = TextDelta | ToolCallChunk | FinishChunk


@dataclass(frozen=True)
class ModelCapabilities:
    """客户端实际支持的能力；不隐式降级。"""

    streaming: bool = True
    tool_calls: bool = False


@dataclass(frozen=True)
class ModelConfig:
    """工厂的连接描述；密钥通过独立运行参数注入，不属于可恢复配置。"""

    model: str
    base_url: str | None = None
