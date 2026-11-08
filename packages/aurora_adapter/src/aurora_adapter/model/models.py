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


class TextPart(TypedDict):
    type: Literal["text"]
    text: str


class ImageSource(TypedDict):
    url: str
    detail: NotRequired[Literal["auto", "low", "high"]]


class ImagePart(TypedDict):
    type: Literal["image_url"]
    image_url: ImageSource


class FileSource(TypedDict, total=False):
    """file_data 为 data URI；file_id 为供应商文件 ID 或其支持的 HTTPS URL。"""

    filename: str
    file_data: str
    file_id: str


class FilePart(TypedDict):
    type: Literal["file"]
    file: FileSource


type ContentPart = TextPart | ImagePart | FilePart
type MessageContent = str | list[ContentPart]


class ThinkingBlock(TypedDict):
    type: Literal["thinking"]
    thinking: str
    signature: str


class RedactedThinkingBlock(TypedDict):
    type: Literal["redacted_thinking"]
    data: str


type ReasoningBlock = ThinkingBlock | RedactedThinkingBlock


class ThinkingConfig(TypedDict):
    type: Literal["enabled", "disabled"]
    budget_tokens: NotRequired[int]


class Message(TypedDict):
    """对话消息；user 可携带文件，assistant 保留思考与工具往返元数据。"""

    role: Literal["system", "user", "assistant", "tool"]
    content: MessageContent
    reasoning_content: NotRequired[str]
    thinking_blocks: NotRequired[list[ReasoningBlock]]
    tool_calls: NotRequired[list[ToolCall]]
    tool_call_id: NotRequired[str]


class ModelRequest(TypedDict):
    """一次模型推理的输入；模型与连接选择由注入的客户端实例承担。"""

    messages: list[Message]
    tools: NotRequired[list[ToolDefinition]]


class ModelResponse(TypedDict):
    """一次推理结果；length/content_filter 结束不等于完整业务回答。"""

    text: str
    reasoning_content: NotRequired[str]
    thinking_blocks: NotRequired[list[ReasoningBlock]]
    tool_calls: list[ToolCall]
    finish_reason: FinishReason


class TextDelta(TypedDict):
    type: Literal["text"]
    text: str


class ReasoningDelta(TypedDict):
    type: Literal["reasoning"]
    text: str


class ThinkingBlockChunk(TypedDict):
    """完整可回传的思考块；签名与不透明数据不用于展示。"""

    type: Literal["thinking_block"]
    block: ReasoningBlock


class ToolCallChunk(TypedDict):
    type: Literal["tool_call"]
    tool_call: ToolCall


class FinishChunk(TypedDict):
    """流的唯一最后片段；迭代结束但没有此片段表示响应不完整。"""

    type: Literal["finish"]
    reason: FinishReason


type ModelChunk = TextDelta | ReasoningDelta | ThinkingBlockChunk | ToolCallChunk | FinishChunk


@dataclass(frozen=True)
class ModelCapabilities:
    """客户端实际支持的能力；不隐式降级。"""

    streaming: bool = True
    tool_calls: bool = False
    file_input: bool = True


@dataclass(frozen=True)
class ModelConfig:
    """工厂的连接描述；密钥通过独立运行参数注入，不属于可恢复配置。"""

    model: str
    base_url: str | None = None
    provider: str | None = None
    capabilities: ModelCapabilities | None = None
    thinking: ThinkingConfig | None = None
    reasoning_effort: Literal["none", "minimal", "low", "medium", "high", "xhigh", "max"] | None = None

    def __post_init__(self) -> None:
        if self.provider is not None and (not isinstance(self.provider, str) or not self.provider.strip()):
            raise ValueError("provider 必须为非空字符串")
        if self.capabilities is not None and (
            not isinstance(self.capabilities, ModelCapabilities)
            or type(self.capabilities.streaming) is not bool
            or type(self.capabilities.tool_calls) is not bool
            or type(self.capabilities.file_input) is not bool
        ):
            raise ValueError("capabilities 必须使用布尔能力值")
        if self.thinking is not None and (
            not isinstance(self.thinking, dict)
            or set(self.thinking) - {"type", "budget_tokens"}
            or self.thinking.get("type") not in ("enabled", "disabled")
            or (
                "budget_tokens" in self.thinking
                and (
                    self.thinking["type"] != "enabled"
                    or type(self.thinking["budget_tokens"]) is not int
                    or self.thinking["budget_tokens"] < 1024
                )
            )
        ):
            raise ValueError("thinking 配置无效；启用时可设置至少 1024 的 budget_tokens")
        if self.reasoning_effort not in (None, "none", "minimal", "low", "medium", "high", "xhigh", "max"):
            raise ValueError("reasoning_effort 无效")
