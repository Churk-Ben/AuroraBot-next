"""通过真实 core 宿主装配控制插件，验证组合执行和取消后的最终落盘。"""

import asyncio

import pytest
from aurora_bot.control import (
    CONTROL_STATE,
    Branch,
    ExecutionPlug,
    ExecutionRequest,
    ExecutionSlot,
    Parallel,
    Serial,
    StateBinding,
    While,
    plugin,
)
from aurora_core.bootstrap import bootstrap
from aurora_core.ctx import Context, StateKey
from aurora_core.discovery import register_plugins
from aurora_core.hooks import HookConnections
from aurora_core.ids import Id
from aurora_core.lifecycle import Lifecycle, LifecycleComponent, install_lifecycle_slots
from aurora_core.persistence import ContextPersistence
from aurora_core.registry import RegistryEntry
from aurora_core.storage import StorageService

DATA = Id("dev.control:state/value")


def environment(root):
    registry = bootstrap()
    register_plugins(registry, (plugin(),))
    registry.register(RegistryEntry(DATA, "state_key", StateKey(), "example"))
    install_lifecycle_slots(registry)
    ctx = Context(registry)
    hooks = HookConnections(registry)
    storage = StorageService(root)
    store = storage.snapshot_store()
    lifecycle = Lifecycle(
        ctx,
        hooks,
        [LifecycleComponent("root")],
        persistence=ContextPersistence(ctx, store),
        storage=storage,
        timeout=0.05,
    )
    return ctx, hooks, lifecycle


def test_composed_control_flow_restores_results_and_execution_records(tmp_path):
    async def scenario():
        ctx, hooks, host = environment(tmp_path)
        count = StateBinding(DATA, (("instance_id", "count"),))
        result = StateBinding(DATA, (("instance_id", "result"),))

        async def increment(request):
            value = count.get(ctx, request)
            assert isinstance(value, int)
            count.set(ctx, request, value + 1)

        async def left(request):
            StateBinding(DATA, (("instance_id", "left"),)).set(ctx, request, "left")

        async def right(request):
            await asyncio.sleep(0)
            StateBinding(DATA, (("instance_id", "right"),)).set(ctx, request, "right")

        parallel_slot = ExecutionSlot("parallel", hooks)
        parallel_slot.connect(ExecutionPlug("left", left))
        parallel_slot.connect(ExecutionPlug("right", right))
        parallel = Parallel(ctx, parallel_slot, concurrency=2)

        branch_slot = ExecutionSlot("branch", hooks)
        branch_slot.connect(parallel.plug)
        branch = Branch(ctx, branch_slot, lambda request: "parallel" if count.get(ctx, request) == 2 else None)

        body_slot = ExecutionSlot("body", hooks)
        body_slot.connect(ExecutionPlug("count", increment, {"count": count}))
        body_slot.connect(branch.plug)
        body = Serial(ctx, body_slot)

        loop_slot = ExecutionSlot("loop", hooks)
        loop_slot.connect(body.plug)
        loop = While(ctx, loop_slot, lambda request: count.get(ctx, request) != 2, max_iterations=2)

        async def finish(request):
            values = [StateBinding(DATA, (("instance_id", name),)).get(ctx, request) for name in ("left", "right")]
            result.set(ctx, request, values)

        root_slot = ExecutionSlot("root", hooks)
        root_slot.connect(loop.plug)
        root_slot.connect(ExecutionPlug("result", finish, {"result": result}))
        request = ExecutionRequest("composed")
        await host.start(configure=lambda: count.set(ctx, request, 0))
        await host.run(Serial(ctx, root_slot).execute, request)
        assert result.get(ctx, request) == ["left", "right"]
        addresses = ctx.list(key=CONTROL_STATE)
        assert len(addresses) == 7
        await host.stop()

        restored, _, restarted = environment(tmp_path)
        await restarted.start()
        assert result.get(restored, request) == ["left", "right"]
        assert restored.list(key=CONTROL_STATE) == addresses
        for address in addresses:
            record = restored.get(address.key, location=dict(address.location))
            assert isinstance(record, dict) and record["status"] == "completed"
        await restarted.stop()

    asyncio.run(scenario())


def test_host_stop_cancels_parallel_work_and_persists_last_writes(tmp_path):
    async def scenario():
        ctx, hooks, host = environment(tmp_path)
        entered = asyncio.Event()
        active = 0

        def worker(name):
            async def execute(request):
                nonlocal active
                active += 1
                if active == 2:
                    entered.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    await asyncio.sleep(0)
                    StateBinding(DATA, (("instance_id", name),)).set(ctx, request, "cleaned")
                    active -= 1

            return ExecutionPlug(name, execute)

        slot = ExecutionSlot("root", hooks)
        slot.connect(worker("first"))
        slot.connect(worker("second"))
        request = ExecutionRequest("cancelled")
        await host.start()
        task = asyncio.create_task(host.run(Parallel(ctx, slot, concurrency=2).execute, request))
        await asyncio.wait_for(entered.wait(), 1)
        await host.stop()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert active == 0

        restored, _, restarted = environment(tmp_path)
        await restarted.start()
        for name in ("first", "second"):
            assert StateBinding(DATA, (("instance_id", name),)).get(restored, request) == "cleaned"
        record = restored.get(
            CONTROL_STATE,
            location={"instance_id": "root", "run_id": request.run_id, "execution_id": request.execution_id},
        )
        assert isinstance(record, dict) and record["status"] == "cancelled"
        await restarted.stop()

    asyncio.run(scenario())
