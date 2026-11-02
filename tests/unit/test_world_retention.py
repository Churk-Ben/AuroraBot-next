"""验证来源保留窗口、裁剪锚点和旧版快照升级的原子行为。"""

from copy import deepcopy

import pytest
from aurora_core.bootstrap import bootstrap
from aurora_core.ctx import Context
from aurora_core.discovery import register_plugins
from aurora_world import RECORDS, CursorError, MessageConflictError, RecordRetention, WorldPosition, WorldRecords
from aurora_world.plugin import plugin


@pytest.fixture
def world():
    registry = bootstrap()
    register_plugins(registry, [plugin()])
    ctx = Context(registry)
    yield ctx, WorldRecords(ctx)
    ctx.close()


def test_retention_is_scoped_atomic_and_keeps_stream_position(world):
    ctx, records = world
    retention = {"time": RecordRetention(1)}
    changes = []
    ctx.subscribe(changes.append, key=RECORDS)
    first = records.append(source_id="time", message_id="1", payload=1, retention=retention).record
    other = records.append(source_id="other", message_id="1", payload="保留").record
    second = records.append(source_id="time", message_id="2", payload=2, retention=retention).record
    assert records.read() == (other, second)
    assert records.read(after=first.position) == (other, second)
    assert len(changes) == 3 and len(changes[-1].value["records"]) == 2
    third = records.append(source_id="time", message_id="3", payload=3, retention=retention).record
    assert records.read() == (other, third)
    assert records.read(after=second.position) == (third,)
    assert third.position.sequence == 4
    with pytest.raises(CursorError):
        records.read(after=first.position)
    with pytest.raises(CursorError):
        records.read(after=WorldPosition(third.position.journal_id, 0))
    with pytest.raises(CursorError):
        records.read(after=WorldPosition(third.position.journal_id, second.position.sequence, "错误锚点"))
    before = ctx.snapshot()
    duplicate = records.append(source_id="time", message_id="3", payload=3, retention=retention)
    assert duplicate.duplicate and duplicate.record == third and ctx.snapshot() == before
    with pytest.raises(MessageConflictError):
        records.append(source_id="time", message_id="3", payload="冲突", retention=retention)
    assert ctx.snapshot() == before


def test_empty_window_keeps_sequence_and_only_retained_messages_are_deduplicated(world):
    ctx, records = world
    assert records.prune({"weather": RecordRetention(4)}) == 0 and ctx.list() == ()
    first = records.append(source_id="weather", message_id="first", payload=0).record
    last = records.append(source_id="weather", message_id="last", payload=1).record
    assert records.prune({"weather": RecordRetention(4, lambda payload: True)}) == 2
    assert records.read() == ()
    assert records.read(after=last.position) == ()
    with pytest.raises(KeyError):
        records.get(source_id="weather", message_id="last")
    replay = records.append(source_id="weather", message_id="first", payload=0)
    assert not replay.duplicate and replay.record.record_id != first.record_id
    assert replay.record.position.sequence == 3
    assert replay.record.position.journal_id == first.position.journal_id
    assert records.read(after=last.position) == (replay.record,)


def test_v1_reads_without_migration_and_mutation_upgrades_without_rewriting_identities(world):
    ctx, records = world
    old = {
        "version": 1,
        "journal_id": "saved",
        "records": [
            {
                "sequence": index,
                "record_id": f"record-{index}",
                "source_id": source,
                "message_id": "1",
                "payload": index,
            }
            for index, source in enumerate(("time", "other"), 1)
        ],
    }
    ctx.set(RECORDS, old)
    original = records.read()
    assert records.prune({"time": RecordRetention(1)}) == 0
    assert ctx.get(RECORDS) == old
    receipt = records.append(source_id="time", message_id="2", payload=3, retention={"time": RecordRetention(1)})
    assert receipt.record.position.sequence == 3
    assert ctx.get(RECORDS)["version"] == 2
    assert records.read()[0] == original[1]
    restored = Context(ctx.registry)
    try:
        restored.restore(ctx.snapshot().records)
        assert WorldRecords(restored).read() == records.read()
        next_record = WorldRecords(restored).append(source_id="other", message_id="2", payload=4).record
        assert next_record.position.sequence == 4
    finally:
        restored.close()
    assert old["version"] == 1 and len(old["records"]) == 2


def test_failed_prune_and_append_leave_the_complete_previous_window(world, monkeypatch):
    ctx, records = world
    records.append(source_id="time", message_id="1", payload={"nested": [1]})
    before = ctx.snapshot()

    def invalid(payload):
        payload["nested"].clear()
        raise ValueError("判断失败")

    with pytest.raises(ValueError, match="判断失败"):
        records.prune({"time": RecordRetention(1, invalid)})
    assert ctx.snapshot() == before
    original = ctx.set

    def fail(*args, **kwargs):
        raise OSError("提交失败")

    monkeypatch.setattr(ctx, "set", fail)
    with pytest.raises(OSError):
        records.append(source_id="time", message_id="2", payload=None, retention={"time": RecordRetention(1)})
    assert ctx.snapshot() == before
    monkeypatch.setattr(ctx, "set", original)
    assert records.append(source_id="time", message_id="2", payload=None).record.position.sequence == 2


@pytest.mark.parametrize(
    "damage",
    [
        lambda data: data.update(next_sequence=True),
        lambda data: data.update(next_sequence=9),
        lambda data: data.update(pruned_through=-1),
        lambda data: data.update(pruned_through=3),
        lambda data: data.update(pruned_record_id=None),
        lambda data: data.update(pruned_record_id=data["records"][0]["record_id"]),
        lambda data: data.update(records=[]),
    ],
)
def test_invalid_v2_sequence_boundaries_are_rejected(world, damage):
    ctx, records = world
    records.append(source_id="time", message_id="1", payload=None)
    records.append(source_id="time", message_id="2", payload=None, retention={"time": RecordRetention(1)})
    value = deepcopy(ctx.get(RECORDS))
    damage(value)
    with pytest.raises((ValueError, TypeError)):
        ctx.set(RECORDS, value)


@pytest.mark.parametrize("limit", [0, -1, True, 1.5])
def test_invalid_retention_limits_are_rejected(limit):
    with pytest.raises(ValueError):
        RecordRetention(limit)
