"""仅安装 core/world 时执行消息接纳、订阅与宿主快照往返。"""

import asyncio
import json
import sys
from pathlib import Path

from aurora_core.bootstrap import bootstrap
from aurora_core.ctx import Context
from aurora_core.discovery import load_plugins, register_plugins
from aurora_core.hooks import HookConnections
from aurora_core.lifecycle import Lifecycle, install_lifecycle_slots
from aurora_core.persistence import ContextPersistence
from aurora_core.storage import StorageService
from aurora_world import RECORDS, WorldRecords


async def main(root):
    registry = bootstrap()
    register_plugins(registry, load_plugins(enabled=["aurora_world"]))
    install_lifecycle_slots(registry)
    ctx = Context(registry)
    storage = StorageService(root)
    host = Lifecycle(
        ctx,
        HookConnections(registry),
        [],
        persistence=ContextPersistence(ctx, storage.snapshot_store(), interval=60),
        storage=storage,
    )
    await host.start()
    records = WorldRecords(ctx)
    observed = []
    handle = ctx.subscribe(observed.append, key=RECORDS, location={})
    try:
        before = records.read()
        receipt = records.append(source_id="workshop/sensor", message_id="first", payload={"text": "世界变化"})
        assert receipt.duplicate is bool(before)
        if before:
            assert receipt.record == before[0]
        new = records.append(source_id="workshop/sensor", message_id=f"next-{len(before)}", payload=None)
        assert not new.duplicate
        assert len(observed) == (1 if before else 2)
        assert records.read(after=receipt.record.position)[-1] == new.record
        result = {
            "duplicate": receipt.duplicate,
            "journal_id": receipt.record.position.journal_id,
            "first_id": receipt.record.record_id,
            "sequences": [record.position.sequence for record in records.read()],
        }
    finally:
        assert ctx.unsubscribe(handle)
        await host.stop()
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main(Path(sys.argv[1])))
