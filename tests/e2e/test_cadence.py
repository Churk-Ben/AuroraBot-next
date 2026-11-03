"""通过默认装配与假模型验收 cadence 的逐条转交、故障和持久恢复。"""

import asyncio
from dataclasses import asdict
from typing import cast

import pytest
import tomli_w
from aurora_bot.assembly import DefaultAssembly
from aurora_bot.cadence import plugin as cadence_plugin
from aurora_bot.cadence.state import CHECKPOINT, CONFIG_STATE
from aurora_control import ExecutionRequest
from aurora_core import Id
from aurora_core.discovery import Plugin
from aurora_core.lifecycle import CLEAN, PREPARE, START, STOP
from aurora_core.registry import RegistryEntry
from aurora_core.snapshots import JsonSnapshotStore
from aurora_world import (
    RECORDS,
    SOURCES,
    RecordRetention,
    SourceInstance,
    SourceSpec,
    SourceUnavailableError,
    WorldRecords,
)
from aurora_world.configuration import plugin as world_configuration_plugin
from aurora_world.plugin import plugin as world_plugin
from test_default_assembly import seed, setup

LOCATION = {"instance_id": "main"}


def configured(root, *, sources=("selected",)):
    path = root / "config/org.aurora.bot/cadence.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(tomli_w.dumps({"source_ids": list(sources)}), encoding="utf-8")
    return setup(root, extra_plugins=(world_plugin(), cadence_plugin()))


def state(ctx):
    return cast(dict, ctx.get(CHECKPOINT, location=LOCATION))


async def until(predicate):
    async with asyncio.timeout(3):
        while not predicate():
            await asyncio.sleep(0)


def append(ctx, identity="one", *, source="selected", payload=None):
    return WorldRecords(ctx).append(
        source_id=source, message_id=identity, payload=identity if payload is None else payload
    )


def test_forwarding_preserves_payload_and_accepts_during_same_run(tmp_path):
    async def scenario():
        host, assembly, ctx, _, clients, _, _, _ = configured(tmp_path)
        await host.start(configure=lambda: seed(ctx, tools=False))
        entered, release = asyncio.Event(), asyncio.Event()
        original = assembly.runtime._activate

        async def hold(request):
            entered.set()
            await release.wait()
            await original(request)

        assembly.runtime._activate = hold
        try:
            ignored = append(ctx, "ignored", source="other")
            payload = {"text": "保留原始内容", "items": [1, False, None, {"nested": "值"}]}
            first = append(ctx, payload=payload)
            await entered.wait()
            handle = assembly.runtime.current
            assert handle is not None
            second = append(ctx, "two", payload=["独立消息"])
            assert append(ctx, payload=payload).duplicate
            await until(lambda: len(state(ctx)["receipts"]) == 2)
            receipts = state(ctx)["receipts"]
            assert [item["message"]["position"] for item in receipts] == [
                asdict(first.record.position),
                asdict(second.record.position),
            ]
            assert ignored.record.position.sequence < receipts[0]["message"]["position"]["sequence"]
            assert {item["run_id"] for item in receipts} == {handle.run_id}
            assert state(ctx)["pending"] is None and not handle.done
            assert assembly.agent is not None
            inbox = assembly.agent.pending(ExecutionRequest("inspect"))
            assert [item["payload"] for item in inbox] == [payload, ["独立消息"]]
            assert [item["id"] for item in inbox] == [item["guidance_id"] for item in receipts]
            release.set()
            assert (await handle.wait()).status == "completed"
            assert clients[0].requests
        finally:
            release.set()
            await host.stop()

    asyncio.run(scenario())


def test_start_reads_backlog_and_restart_does_not_replay_receipts(tmp_path):
    async def scenario():
        for restart in (False, True):
            host, assembly, ctx, _, clients, _, _, _ = configured(tmp_path)

            def configure(ctx=ctx, restart=restart):
                seed(ctx, tools=False)
                if not restart:
                    append(ctx)

            await host.start(configure=configure)
            try:
                await until(lambda ctx=ctx: len(state(ctx)["receipts"]) == 1)
                if not restart:
                    await until(lambda assembly=assembly: assembly.runtime.current is None)
                    assert clients[0].requests
                    saved = state(ctx)
                else:
                    for _ in range(4):
                        await asyncio.sleep(0)
                    assert clients[0].requests == [] and state(ctx) == saved
                    assert append(ctx).duplicate
                    append(ctx, "two")
                    await until(lambda ctx=ctx: len(state(ctx)["receipts"]) == 2)
                    assert state(ctx)["receipts"][0] == saved["receipts"][0]
                    await until(lambda assembly=assembly: assembly.runtime.current is None)
            finally:
                await host.stop()
            snapshot = JsonSnapshotStore(tmp_path / "framework/ctx.json").load()
            assert any(item.address.key == CHECKPOINT for item in snapshot)
            assert all(item.address.key != CONFIG_STATE for item in snapshot)

    asyncio.run(scenario())


@pytest.mark.parametrize("fault", ["before_submit", "after_submit", "commit"])
def test_uncertain_transfer_pauses_without_replay_even_after_restart(tmp_path, monkeypatch, fault):
    async def scenario():
        host, assembly, ctx, _, _, _, _, _ = configured(tmp_path)
        await host.start(configure=lambda: seed(ctx, tools=False))
        submit, write = assembly.runtime.submit, ctx.set
        submissions = []

        def faulty_submit(payload, **kwargs):
            if fault == "after_submit":
                submissions.append(submit(payload, **kwargs))
            raise RuntimeError("不可保存的异常详情")

        def faulty_write(key, value, **kwargs):
            if key == CHECKPOINT and value["receipts"]:
                raise RuntimeError("回执写入失败")
            write(key, value, **kwargs)

        if fault == "commit":
            monkeypatch.setattr(ctx, "set", faulty_write)
        else:
            monkeypatch.setattr(assembly.runtime, "submit", faulty_submit)
        try:
            append(ctx)
            await until(lambda: state(ctx)["error"] == "TransferUncertain")
            assert state(ctx)["position"] is None and state(ctx)["pending"]["message_id"] == "one"
            append(ctx, "two")
            await asyncio.sleep(0)
            assert state(ctx)["receipts"] == []
            assert len(submissions) == (1 if fault == "after_submit" else 0)
        finally:
            await host.stop()
        assert "不可保存的异常详情" not in (tmp_path / "framework/ctx.json").read_text(encoding="utf-8")
        restored, other, other_ctx, _, clients, _, _, _ = configured(tmp_path)
        await restored.start()
        try:
            append(other_ctx, "three")
            await asyncio.sleep(0)
            assert clients[0].requests == [] and other.runtime.current is None
            assert state(other_ctx)["error"] == "TransferUncertain"
            assert state(other_ctx)["pending"]["message_id"] == "one"
        finally:
            await restored.stop()

    asyncio.run(scenario())


@pytest.mark.parametrize("fault", ["pruned", "journal", "selection", "pending"])
def test_recovery_requires_matching_cursor_and_resolved_intent(tmp_path, fault):
    async def scenario():
        host, assembly, ctx, _, _, _, _, _ = configured(tmp_path)
        await host.start(configure=lambda: seed(ctx, tools=False))
        append(ctx)
        await until(lambda: len(state(ctx)["receipts"]) == 1)
        await until(lambda: assembly.runtime.current is None)
        await host.stop()
        if fault == "selection":
            (tmp_path / "config/org.aurora.bot/cadence.toml").write_text('source_ids = ["other"]', encoding="utf-8")
        restored, other, other_ctx, _, clients, _, _, _ = configured(tmp_path)

        def configure():
            if fault == "pruned":
                append(other_ctx, "two")
                append(other_ctx, "three")
                WorldRecords(other_ctx).prune({"selected": RecordRetention(1)})
            elif fault == "journal":
                other_ctx.delete(RECORDS)
                append(other_ctx)
            elif fault == "pending":
                record = append(other_ctx, "two").record
                other_ctx.set(
                    CHECKPOINT,
                    {
                        **state(other_ctx),
                        "pending": {
                            "position": asdict(record.position),
                            "source_id": record.source_id,
                            "message_id": record.message_id,
                            "payload": record.payload,
                        },
                    },
                    location=LOCATION,
                )

        await restored.start(configure=configure)
        try:
            expected = {
                "pruned": "CursorInvalid",
                "journal": "CursorInvalid",
                "selection": "SelectionChanged",
                "pending": "TransferUncertain",
            }[fault]
            await until(lambda: state(other_ctx)["error"] == expected)
            assert clients[0].requests == [] and other.runtime.current is None
            assert (await other.runtime.submit("暂停世界转发期间的直接交流").run.wait()).status == "completed"
            assert state(other_ctx)["error"] == expected
        finally:
            await restored.stop()

    asyncio.run(scenario())


def test_empty_selection_and_immediate_shutdown_do_not_leave_tasks(tmp_path):
    async def scenario():
        host, _, ctx, _, clients, _, _, _ = configured(tmp_path, sources=())
        await host.start(configure=lambda: seed(ctx, tools=False))
        append(ctx)
        await asyncio.sleep(0)
        assert clients[0].requests == [] and ctx.list(key=CHECKPOINT) == ()
        await host.stop()
        (tmp_path / "config/org.aurora.bot/cadence.toml").write_text('source_ids = ["selected"]', encoding="utf-8")
        restored, _, _, _, _, _, _, _ = configured(tmp_path)
        await restored.start()
        await restored.stop()
        assert not [task for task in asyncio.all_tasks() if task.get_name().startswith("cadence-")]

    asyncio.run(scenario())


def test_cancel_waits_for_cleanup_then_accepts_next_world_message(tmp_path):
    async def scenario():
        host, assembly, ctx, _, _, _, _, _ = configured(tmp_path)
        await host.start(configure=lambda: seed(ctx, tools=False))
        entered, cleaning, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
        original = assembly.runtime._activate
        calls = 0

        async def hold(request):
            nonlocal calls
            calls += 1
            if calls == 1:
                try:
                    entered.set()
                    await asyncio.Event().wait()
                finally:
                    cleaning.set()
                    await release.wait()
            await original(request)

        assembly.runtime._activate = hold
        try:
            append(ctx)
            await entered.wait()
            handle = assembly.runtime.current
            assert handle is not None
            cancel = asyncio.create_task(assembly.runtime.cancel(handle.run_id))
            await cleaning.wait()
            append(ctx, "two")
            for _ in range(4):
                await asyncio.sleep(0)
            assert len(state(ctx)["receipts"]) == 1 and state(ctx)["error"] is None
            release.set()
            assert await cancel
            await until(lambda: len(state(ctx)["receipts"]) == 2)
            assert state(ctx)["receipts"][1]["run_id"] != handle.run_id
            await until(lambda: assembly.runtime.current is None)
        finally:
            release.set()
            await host.stop()

    asyncio.run(scenario())


@pytest.mark.parametrize("fail_start", [False, True])
def test_source_lifecycle_and_partial_start_cleanup(tmp_path, fail_start):
    async def scenario():
        events = []
        emitters = []
        source = Id("dev.cadence:sources/test")

        async def factory(*, source_id, emit, config):
            emitters.append(emit)

            async def start():
                events.append("start")
                emit(message_id="one", payload="启动消息")
                if fail_start:
                    raise RuntimeError("来源启动失败")

            async def stop():
                events.append("stop")
                with pytest.raises(SourceUnavailableError):
                    emit(message_id="late", payload="关闭时拒绝")

            async def close():
                events.append("close")

            return SourceInstance(start, stop, close)

        for relative, value in (
            ("org.aurora.bot/cadence.toml", {"source_ids": ["selected"]}),
            ("org.aurora.world/config.toml", {"sources": [{"source": str(source), "source_id": "selected"}]}),
        ):
            path = tmp_path / "config" / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(tomli_w.dumps(value), encoding="utf-8")
        host, assembly, ctx, _, clients, _, _, _ = setup(
            tmp_path,
            extra_plugins=(
                world_plugin(),
                world_configuration_plugin(),
                cadence_plugin(),
                Plugin("test", (RegistryEntry(source, "source", SourceSpec(factory), "test", register_to=SOURCES),)),
            ),
        )
        if fail_start:
            with pytest.raises(RuntimeError, match="来源启动失败"):
                await host.start(configure=lambda: seed(ctx, tools=False))
        else:
            await host.start(configure=lambda: seed(ctx, tools=False))
            await until(lambda: len(state(ctx)["receipts"]) == 1)
            await until(lambda: assembly.runtime.current is None)
        await host.stop()
        assert events == ["start", "stop", "close"] and clients[0].closed
        with pytest.raises(SourceUnavailableError):
            emitters[0](message_id="closed", payload="关闭后拒绝")
        assert not [task for task in asyncio.all_tasks() if task.get_name().startswith("cadence-")]
        snapshot = JsonSnapshotStore(tmp_path / "framework/ctx.json").load()
        world = cast(dict, next(item.value for item in snapshot if item.address.key == RECORDS))
        assert [item["message_id"] for item in world["records"]] == ["one"]

    asyncio.run(scenario())


def test_component_connection_failure_releases_cadence_links(tmp_path):
    _, assembly, ctx, registry, _, _, _, _ = configured(tmp_path)

    def fail(*args, **kwargs):
        raise RuntimeError("世界组件连接失败")

    registry.register_many(world_configuration_plugin().entries)
    other = DefaultAssembly(
        registry=registry,
        ctx=ctx,
        hooks=assembly.hooks,
        storage=assembly.storage,
        instance_id="failed",
        world_component_factory=fail,
    )
    try:
        with pytest.raises(RuntimeError, match="世界组件连接失败"):
            other.components()
        for owner in ("failed/model", "failed/bot", "failed/cadence"):
            for phase in (PREPARE, START, STOP, CLEAN):
                assert assembly.hooks.for_slot(phase, owner) == ()
    finally:
        assembly.hooks.close()
        assembly.storage.close()
        ctx.close()
