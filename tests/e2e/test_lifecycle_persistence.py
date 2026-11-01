"""验证组件最终写入、宿主落盘与失败后的恢复边界。"""

import asyncio

import pytest
from aurora_core import Id, entry_from, hook_handler
from aurora_core.bootstrap import bootstrap
from aurora_core.ctx import Context, StateKey
from aurora_core.hooks import HookConnections
from aurora_core.lifecycle import CLEAN, PREPARE, STOP, Lifecycle, LifecycleComponent, install_lifecycle_slots
from aurora_core.persistence import ContextPersistence
from aurora_core.registry import RegistryEntry
from aurora_core.storage import StorageService

VALUE = Id("dev.lifecycle:state/value")


def environment(root):
    registry = bootstrap()
    install_lifecycle_slots(registry)
    registry.register(RegistryEntry(VALUE, "state_key", StateKey(), "测试插件"))
    ctx = Context(registry)
    hooks = HookConnections(registry)
    storage = StorageService(root)
    store = storage.snapshot_store()
    persistence = ContextPersistence(ctx, store, interval=60)
    lifecycle = Lifecycle(ctx, hooks, [LifecycleComponent("app")], persistence=persistence, storage=storage)
    return registry, ctx, hooks, storage, store, lifecycle


@pytest.mark.parametrize("stop_handler", [True, False])
@pytest.mark.parametrize("phase", [STOP, CLEAN])
def test_final_snapshot_is_host_owned_and_restored_before_prepare(tmp_path, stop_handler, phase):
    async def scenario():
        registry, ctx, hooks, storage, _, lifecycle = environment(tmp_path)

        @hook_handler("dev.lifecycle:handlers/stop", slot=phase)
        def stop():
            storage.set("dev.lifecycle", "finished", True)
            ctx.set(VALUE, "stopped")

        registry.register(entry_from(stop, provider="测试插件"))
        connection = hooks.connect(
            phase, Id("dev.lifecycle:handlers/stop"), slot_instance="app", handler_instance="app"
        )
        if not stop_handler:
            hooks.disconnect(connection)
        await lifecycle.start()
        ctx.set(VALUE, "running")
        await lifecycle.stop()
        with pytest.raises(RuntimeError, match="关闭"):
            storage.keys("dev.lifecycle")
        with pytest.raises(RuntimeError, match="关闭"):
            ctx.list()

        registry, ctx, hooks, storage, _, lifecycle = environment(tmp_path)
        restored = []

        @hook_handler("dev.lifecycle:handlers/prepare", slot=PREPARE)
        def prepare():
            restored.append(ctx.get(VALUE))

        registry.register(entry_from(prepare, provider="测试插件"))
        hooks.connect(PREPARE, Id("dev.lifecycle:handlers/prepare"), slot_instance="app", handler_instance="app")
        await lifecycle.start()
        assert restored == ["stopped" if stop_handler else "running"]
        if stop_handler:
            assert storage.get("dev.lifecycle", "finished") is True
        await lifecycle.stop()

    asyncio.run(scenario())


def test_final_flush_failure_preserves_state_and_storage_for_retry(tmp_path, monkeypatch):
    async def scenario():
        registry, ctx, hooks, storage, store, lifecycle = environment(tmp_path)
        stopped = []

        @hook_handler("dev.lifecycle:handlers/stop", slot=STOP)
        def stop():
            stopped.append(True)
            ctx.set(VALUE, "final")

        registry.register(entry_from(stop, provider="测试插件"))
        hooks.connect(STOP, Id("dev.lifecycle:handlers/stop"), slot_instance="app", handler_instance="app")
        await lifecycle.start()
        save = store.save

        def fail(snapshot):
            raise OSError("落盘失败")

        monkeypatch.setattr(store, "save", fail)
        with pytest.raises(OSError, match="落盘失败"):
            await lifecycle.stop()
        assert lifecycle.state == "failed"
        assert ctx.get(VALUE) == "final"
        storage.set("dev.lifecycle", "retry", True)
        monkeypatch.setattr(store, "save", save)
        await lifecycle.stop()
        assert stopped == [True]
        assert store.load()[0].value == "final"
        assert lifecycle.state == "stopped"

    asyncio.run(scenario())


def test_restore_failure_preserves_bad_snapshot_and_closes_resources(tmp_path):
    async def scenario():
        _, ctx, _, storage, store, lifecycle = environment(tmp_path)
        store.path.write_text("invalid JSON", encoding="utf-8")
        with pytest.raises(ValueError):
            await lifecycle.start()
        assert store.path.read_text(encoding="utf-8") == "invalid JSON"
        assert lifecycle.state == "stopped"
        with pytest.raises(RuntimeError, match="关闭"):
            storage.keys("dev.lifecycle")
        with pytest.raises(RuntimeError, match="关闭"):
            ctx.list()

    asyncio.run(scenario())
