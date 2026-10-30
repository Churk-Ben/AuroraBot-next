"""在途调用、并发快照与最后写入共存时的实际关闭顺序。"""

import asyncio
from threading import Event

import pytest
from aurora_core import Id, entry_from, hook_handler
from aurora_core.bootstrap import bootstrap
from aurora_core.ctx import Context, StateKey
from aurora_core.hooks import HookConnections
from aurora_core.lifecycle import STOP, Lifecycle, LifecycleComponent, install_lifecycle_slots
from aurora_core.persistence import ContextPersistence
from aurora_core.registry import RegistryEntry
from aurora_core.snapshots import JsonSnapshotStore
from aurora_core.storage import StorageService

KEY = Id("dev.m1:state/value")


def test_shutdown_drains_writers_before_final_snapshot_and_resource_release(tmp_path):
    async def scenario():
        trace = []
        entered = Event()
        release_io = Event()
        work_entered = asyncio.Event()
        release_work = asyncio.Event()
        gate_closed = asyncio.Event()
        registry = bootstrap()
        install_lifecycle_slots(registry)
        registry.register(RegistryEntry(KEY, "state_key", StateKey(), "m1"))

        class TracedContext(Context):
            def close(self):
                super().close()
                trace.append("ctx:closed")

        class TracedStorage(StorageService):
            def close(self):
                super().close()
                trace.append("storage:closed")

        class TracedStore(JsonSnapshotStore):
            def save(self, snapshot):
                if not entered.is_set():
                    entered.set()
                    if not release_io.wait(5):
                        raise TimeoutError("未释放测试 I/O")
                super().save(snapshot)
                trace.append(f"saved:{snapshot.revision}")

        ctx = TracedContext(registry)
        hooks = HookConnections(registry)
        storage = TracedStorage(tmp_path)
        store = TracedStore(storage.snapshot_store().path)
        persistence = ContextPersistence(ctx, store, interval=3600)
        changes = []
        ctx.subscribe(lambda change: changes.append(change))

        def close_gate():
            trace.append("gate:closed")
            gate_closed.set()

        @hook_handler("dev.m1:handlers/stop", slot=STOP)
        def stop():
            storage.set("dev.m1", "stopped", True)
            ctx.set(KEY, "stopped")
            trace.append("component:stopped")

        registry.register(entry_from(stop, provider="m1"))
        hooks.connect(STOP, Id("dev.m1:handlers/stop"), slot_instance="app", handler_instance="app")
        lifecycle = Lifecycle(
            ctx, hooks, [LifecycleComponent("app", stop_accepting=close_gate)], persistence=persistence, storage=storage
        )
        await lifecycle.start()
        ctx.set(KEY, "initial")
        flush = asyncio.create_task(persistence.flush())

        async def work(index):
            work_entered.set()
            await release_work.wait()
            ctx.set(KEY, index, location={"writer": str(index)})
            trace.append(f"work:{index}")

        workers = []
        stopping = None
        try:
            assert await asyncio.to_thread(entered.wait, 3)
            workers = [asyncio.create_task(lifecycle.run(work, index)) for index in range(20)]
            await asyncio.wait_for(work_entered.wait(), 3)
            stopping = asyncio.create_task(lifecycle.stop())
            await asyncio.wait_for(gate_closed.wait(), 3)
            with pytest.raises(RuntimeError, match="新工作"):
                await lifecycle.run(lambda: None)
            release_work.set()
            await asyncio.gather(*workers)
            # stop handler 必须已经结束才能解除磁盘屏障。
            async with asyncio.timeout(3):
                while "component:stopped" not in trace:
                    await asyncio.sleep(0)
            assert "storage:closed" not in trace
            assert ctx.get(KEY) == "stopped"
        finally:
            release_work.set()
            release_io.set()
            await flush
            if stopping is not None:
                await stopping
            else:
                await lifecycle.stop()
        assert trace[0] == "gate:closed"
        component_index = trace.index("component:stopped")
        assert all(trace.index(f"work:{index}") < component_index for index in range(20))
        assert trace[-3:] == ["saved:22", "storage:closed", "ctx:closed"]
        assert [change.revision for change in changes] == list(range(1, 23))
        assert changes[-1].value == "stopped"
        with pytest.raises(RuntimeError, match="关闭"):
            hooks.for_slot(STOP, "app")
        restored = Context(registry)
        restored.restore(store.load())
        assert restored.get(KEY) == "stopped"
        assert all(restored.get(KEY, location={"writer": str(index)}) == index for index in range(20))
        restored.close()
        with StorageService(tmp_path) as reopened:
            assert reopened.get("dev.m1", "stopped") is True

    asyncio.run(scenario())
