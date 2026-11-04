"""模型调用及资源所有权；接口与具体供应商 SDK 无关。"""

from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager
from copy import deepcopy
from typing import Protocol

from .models import FinishReason, ModelCapabilities, ModelChunk, ModelConfig, ModelRequest, ModelResponse, ToolCall


class ModelError(RuntimeError):
    """适配器对外报告的模型错误；取消与超时保留 Python 标准异常。"""


class UnsupportedCapability(ModelError):
    """请求使用了客户端未声明支持的能力。"""


class ModelProtocolError(ModelError):
    """响应流缺少结束片段或违反片段顺序。"""


class ModelClient(Protocol):
    """调用方关闭每次响应流，创建客户端的宿主在全部调用结束后 aclose。

    stream 必须通过 async with 使用，提前退出、失败或取消均释放该次响应资源。
    取消传播为 CancelledError，不生成成功结束片段；超时由调用方设置 asyncio.timeout。
    并发能力由具体客户端约定，本协议不保证所有适配器可同时接受多次调用。
    """

    @property
    def capabilities(self) -> ModelCapabilities: ...

    async def complete(self, request: ModelRequest) -> ModelResponse: ...

    def stream(self, request: ModelRequest) -> AbstractAsyncContextManager[AsyncIterator[ModelChunk]]: ...

    async def aclose(self) -> None: ...


class ModelFactory(Protocol):
    """创建独立模型实例；api_key 仅在运行期传入，不写入 ctx。"""

    async def __call__(self, config: ModelConfig, *, api_key: str | None = None) -> ModelClient: ...


def require_capabilities(client: ModelClient, request: ModelRequest, *, streaming: bool) -> None:
    if streaming and not client.capabilities.streaming:
        raise UnsupportedCapability("模型不支持流式响应")
    uses_tools = request.get("tools") or any(
        message.get("tool_calls") or message["role"] == "tool" for message in request["messages"]
    )
    if uses_tools and not client.capabilities.tool_calls:
        raise UnsupportedCapability("模型不支持工具调用")


class ResponseBuffer:
    """收集一次流的当前结果；不保存片段历史，可供调用组件持续写入同一 ctx 位置。"""

    def __init__(self) -> None:
        self.text = ""
        self.tool_calls: list[ToolCall] = []
        self.finish_reason: FinishReason | None = None

    def append(self, chunk: ModelChunk) -> None:
        if self.finish_reason is not None:
            raise ModelProtocolError("结束片段之后不得再输出内容")
        if chunk["type"] == "text":
            self.text += chunk["text"]
        elif chunk["type"] == "tool_call":
            call = chunk["tool_call"]
            if any(previous["id"] == call["id"] for previous in self.tool_calls):
                raise ModelProtocolError(f"工具调用 ID 重复：{call['id']}")
            self.tool_calls.append(deepcopy(call))
        else:
            self.finish_reason = chunk["reason"]

    def result(self) -> ModelResponse:
        if self.finish_reason is None:
            raise ModelProtocolError("响应流缺少结束片段")
        if self.finish_reason == "tool_calls" and not self.tool_calls:
            raise ModelProtocolError("工具调用结束必须提供完整工具请求")
        return {"text": self.text, "tool_calls": deepcopy(self.tool_calls), "finish_reason": self.finish_reason}


async def collect_response(chunks: AsyncIterator[ModelChunk]) -> ModelResponse:
    """在响应流的上下文内收集完整结果；资源关闭仍由外层 async with 负责。"""
    buffer = ResponseBuffer()
    async for chunk in chunks:
        buffer.append(chunk)
    return buffer.result()
