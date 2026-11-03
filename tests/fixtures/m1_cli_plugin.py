"""真实 CLI 进程验收插件：发布状态、触发 SIGINT，并提供收尾故障注入。"""

import asyncio
import os
import signal
from dataclasses import replace

from aurora_core import Id, entry_from, hook_handler
from aurora_core.ctx import StateKey
from aurora_core.discovery import Plugin
from aurora_core.lifecycle import PREPARE, START, STOP, LifecycleComponent
from aurora_core.registry import RegistryEntry
from aurora_core.snapshots import JsonSnapshotStore

KEY = Id("dev.m1:state/value")
ASSEMBLY = Id("dev.m1:assemblies/watch")


def assemble(*, registry, ctx, hooks, storage, workspace_root):
    fault = os.environ.get("AURORA_M1_FAULT", "")
    ready = asyncio.Event()
    worker = None
    subscription = None
    trace = storage.directory("dev.m1") / "events.txt"

    def record(value):
        with trace.open("a", encoding="utf-8") as stream:
            stream.write(f"{value}\n")

    original = registry.get(Id("org.aurora.core:operations/ctx/subscribe"))

    def subscribe(callback, **filters):
        handle = ctx.subscribe(callback, **filters)
        ready.set()
        return handle

    registry.replace(replace(original, target=subscribe))

    class FailingStore(JsonSnapshotStore):
        def save(self, snapshot):
            raise OSError("M1 最终落盘故障")

    if fault == "flush":
        path = storage.snapshot_store().path
        storage.snapshot_store = lambda: FailingStore(path)

    @hook_handler("dev.m1:handlers/prepare", slot=PREPARE)
    def prepare():
        nonlocal subscription
        subscription = ctx.subscribe(lambda change: record(change.value), key=KEY)

    async def produce():
        await ready.wait()
        ctx.set(KEY, "first")
        await asyncio.sleep(0)
        ctx.set(KEY, "second")
        await asyncio.sleep(0)
        signal.raise_signal(signal.SIGINT)

    @hook_handler("dev.m1:handlers/start", slot=START)
    def start():
        nonlocal worker
        worker = asyncio.create_task(produce())

    @hook_handler("dev.m1:handlers/stop", slot=STOP)
    async def stop():
        if worker is not None:
            await worker
        if fault == "stop":
            raise RuntimeError("M1 组件停止故障")
        ctx.set(KEY, "stopped")
        if subscription is not None:
            ctx.unsubscribe(subscription)
        record("source:closed")

    for phase, handler in ((PREPARE, prepare), (START, start), (STOP, stop)):
        entry = entry_from(handler, provider="m1_fixture")
        registry.register(entry)
        hooks.connect(phase, entry.id, slot_instance="app", handler_instance="app")
    return [LifecycleComponent("app", stop_accepting=lambda: record("gate:closed"))]


def plugin():
    return Plugin(
        "m1_fixture",
        (
            RegistryEntry(KEY, "state_key", StateKey(), "m1_fixture"),
            RegistryEntry(ASSEMBLY, "assembly", assemble, "m1_fixture"),
        ),
    )
