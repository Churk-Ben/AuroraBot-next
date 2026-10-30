"""离线模型调用示例：准备输入、流式回答与结果读取；启动方法见 examples/START.md。"""

import argparse
import asyncio
import math
import sys
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path
from uuid import uuid4

from aurora_bot.control import (
    CONTROL_STATE,
    ExecutionPlug,
    ExecutionRequest,
    ExecutionSlot,
    Serial,
    StateBinding,
    component_entries,
    plugin,
)
from aurora_bot.model import ModelCall
from aurora_bot.model import plugin as model_plugin
from aurora_core import Id, entry_from, hook_handler
from aurora_core.bootstrap import bootstrap
from aurora_core.ctx import Context, StateChange, StateKey
from aurora_core.discovery import register_plugins
from aurora_core.hooks import HookConnections
from aurora_core.lifecycle import STOP, Lifecycle, LifecycleComponent, install_lifecycle_slots
from aurora_core.persistence import ContextPersistence
from aurora_core.registry import DefinitionRegistry, RegistryEntry
from aurora_core.storage import StorageService
from aurora_model_adapter import ModelError, ModelRequest
from aurora_model_adapter.fake import FakeModel, FakeReply

INPUT = Id("dev.example.model:state/input")
OUTPUT = Id("dev.example.model:state/output")


def make_plug(
    registry: DefinitionRegistry,
    definition_id: Id,
    execute: Callable[[ExecutionRequest], Awaitable[None]],
    states: Mapping[str, StateBinding] | None = None,
    *,
    instance_id: str,
) -> ExecutionPlug:
    """由示例装配显式登记局部业务组件，再绑定具体执行实例。"""
    registry.register_many(component_entries(definition_id, execute, execute, provider="dev.example.model"))
    return ExecutionPlug(definition_id, execute, states or {}, instance_id=instance_id)


def observe(change: StateChange) -> None:
    """从同一状态的前后文本计算本次增量，不将片段历史写入 ctx。"""
    if change.action != "set":
        return
    value = change.value
    assert isinstance(value, dict)
    previous = change.previous if isinstance(change.previous, dict) else {}
    print(value["text"][len(previous.get("text", "")) :], end="", flush=True)
    if value["status"] != "running":
        print(f"\n状态: {value['status']}", flush=True)


async def run(data_dir: Path, text: str, delay: float, fail: bool, streaming: bool) -> None:
    registry = bootstrap()
    register_plugins(registry, (plugin(), model_plugin()))
    install_lifecycle_slots(registry)
    for key in (INPUT, OUTPUT):
        registry.register(RegistryEntry(key, "state_key", StateKey(), "model_call_example"))
    ctx = Context(registry)
    hooks = HookConnections(registry)
    input_state = StateBinding(INPUT)
    output_state = StateBinding(OUTPUT, (("instance_id", "model"),))

    def respond(request: ModelRequest) -> FakeReply:
        parts = ("假模型收到：", request["messages"][-1]["content"])
        if fail:
            return FakeReply(parts, error=ModelError("模拟调用失败"))
        return FakeReply((*parts, "。"))

    client = FakeModel(respond, delay=delay)
    model = ModelCall(
        ctx, client, instance_id="model", request_state=input_state, output_state=output_state, streaming=streaming
    )
    slot = ExecutionSlot(Serial.definition_id, hooks, instance_id="root")

    async def prepare(request: ExecutionRequest) -> None:
        input_state.set(ctx, request, {"messages": [{"role": "user", "content": text}]})

    async def finish(request: ExecutionRequest) -> None:
        value = output_state.get(ctx, request)
        assert isinstance(value, dict)
        print(f"结束原因: {value['finish_reason']}", flush=True)

    slot.connect(
        make_plug(
            registry, Id("dev.example.model:handlers/prepare"), prepare, {"output": input_state}, instance_id="prepare"
        )
    )
    slot.connect(model.plug)
    slot.connect(
        make_plug(
            registry, Id("dev.example.model:handlers/finish"), finish, {"input": output_state}, instance_id="finish"
        )
    )
    root = Serial(ctx, slot)

    @hook_handler("dev.example.model:handlers/close", slot=STOP)
    async def close_model() -> None:
        await client.aclose()

    close_entry = entry_from(close_model, provider="model_call_example")
    registry.register(close_entry)
    hooks.connect(STOP, close_entry.id, slot_instance="model", handler_instance="model")
    storage = StorageService(data_dir)
    host = Lifecycle(
        ctx,
        hooks,
        [LifecycleComponent("model"), LifecycleComponent("root", depends_on=("model",))],
        persistence=ContextPersistence(ctx, storage.snapshot_store()),
        storage=storage,
    )

    def configure() -> None:
        for address in ctx.list(key=CONTROL_STATE):
            ctx.delete(address.key, location=dict(address.location))

    request = ExecutionRequest(uuid4().hex)
    await host.start(configure=configure)
    subscription = ctx.subscribe(observe, key=OUTPUT)
    try:
        print(f"运行 ID: {request.run_id}", flush=True)
        await host.run(root.execute, request)
    finally:
        ctx.unsubscribe(subscription)
        try:
            for key in (INPUT, OUTPUT):
                for address in ctx.list(key=key):
                    if address != output_state.address(request):
                        ctx.delete(address.key, location=dict(address.location))
        finally:
            await host.stop()
    print(f"快照: {data_dir / 'framework' / 'ctx.json'}")


def main() -> None:
    parser = argparse.ArgumentParser(description="用确定性假模型观察 ctx 流式输出，无需网络或密钥")
    parser.add_argument("--data-dir", type=Path, required=True, help="此示例独占的数据目录")
    parser.add_argument("--text", default="你好", help="输入文本")
    parser.add_argument("--delay", type=float, default=0.2, help="每个片段等待秒数")
    parser.add_argument("--fail", action="store_true", help="输出部分文本后模拟模型失败")
    parser.add_argument("--no-stream", action="store_true", help="显式使用完整响应接口")
    args = parser.parse_args()
    if not math.isfinite(args.delay) or args.delay < 0:
        parser.error("--delay 必须为非负有限数")
    try:
        asyncio.run(run(args.data_dir, args.text, args.delay, args.fail, not args.no_stream))
    except KeyboardInterrupt:
        print("已取消。")
        raise SystemExit(130) from None
    except ModelError as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
