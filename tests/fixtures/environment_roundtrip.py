"""独立安装的环境来源验收；--live-weather 显式访问一次真实天气服务。"""

import argparse
import asyncio
import json
from dataclasses import replace
from functools import partial
from pathlib import Path
from typing import cast

import httpx
from aurora_config import configuration_component, copy_missing
from aurora_core.bootstrap import bootstrap
from aurora_core.ctx import Context
from aurora_core.discovery import load_plugins, register_plugins
from aurora_core.hooks import HookConnections
from aurora_core.lifecycle import Lifecycle, install_lifecycle_slots
from aurora_core.persistence import ContextPersistence
from aurora_core.storage import StorageService
from aurora_world import RECORDS, SourceSpec, WorldRecords
from aurora_world.configuration import configured_sources_component
from aurora_world.environment import TIME, WEATHER, create_time, create_weather


async def main(root: Path, *, live_weather: bool) -> None:
    registry = bootstrap()
    register_plugins(
        registry,
        load_plugins(
            enabled=[
                "aurora_config",
                "aurora_world",
                "aurora_world.configuration",
                "aurora_world.environment",
            ]
        ),
    )
    install_lifecycle_slots(registry)
    ctx, hooks, storage = Context(registry), HookConnections(registry), StorageService(root)
    copy_missing(
        storage.configuration_directory() / "org.aurora.world/config.toml",
        """
[[sources]]
source = "org.aurora.world:sources/environment/time"
source_id = "environment/time"
[sources.config]
interval_seconds = 60

[[sources]]
source = "org.aurora.world:sources/environment/weather"
source_id = "environment/weather"
[sources.config]
place = "南京"
latitude = 32.0617
longitude = 118.7778
interval_seconds = 900
timeout_seconds = 10
""".encode(),
    )
    settled, sampled = asyncio.Event(), []

    async def sleep(seconds):
        sampled.append(seconds)
        if len(sampled) == 2:
            settled.set()
        await asyncio.Event().wait()

    def response(request):
        return httpx.Response(
            200,
            json={
                "current": {"time": 1793606400, "temperature_2m": 18.5, "weather_code": 2, "wind_speed_10m": 6.2},
                "current_units": {"temperature_2m": "°C", "wind_speed_10m": "km/h"},
            },
        )

    for identity, factory in (
        (TIME, partial(create_time, sleep=sleep)),
        (
            WEATHER,
            partial(create_weather, sleep=sleep, transport=None if live_weather else httpx.MockTransport(response)),
        ),
    ):
        registry.replace(replace(registry.get(identity), target=SourceSpec(factory)))
    store = storage.snapshot_store()
    before = next((cast(dict, record.value)["records"] for record in store.load() if record.address.key == RECORDS), [])
    host = Lifecycle(
        ctx,
        hooks,
        [
            configuration_component(registry, ctx, hooks, storage),
            configured_sources_component(ctx, hooks),
        ],
        persistence=ContextPersistence(ctx, store),
        storage=storage,
    )
    await host.start()
    try:
        await asyncio.wait_for(settled.wait(), timeout=15)
        records = WorldRecords(ctx).read()
        assert len(records) == len(before) + 2
        assert len({record.message_id for record in records}) == len(records)
        result = {"count": len(records), "observations": [record.payload for record in records[-2:]]}
    finally:
        await host.stop()
    assert [record.address.key for record in store.load()] == [RECORDS]
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--live-weather", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(args.root, live_weather=args.live_weather))
