"""用可控时钟和模拟传输验证环境采样、故障恢复及关闭边界。"""

import asyncio
from datetime import UTC, datetime, timedelta
from functools import partial
from time import time
from typing import cast

import httpx
import pytest
from aurora_core import Id
from aurora_core.bootstrap import bootstrap
from aurora_core.ctx import Context
from aurora_core.discovery import register_plugins
from aurora_core.hooks import HookConnections
from aurora_core.lifecycle import install_lifecycle_slots
from aurora_core.registry import RegistryEntry
from aurora_world import SOURCES, SourceSpec, WorldRecords, WorldSources
from aurora_world.environment import TIME_CONFIG, WEATHER_CONFIG, create_time, create_weather
from aurora_world.plugin import plugin

LOCATION = {"place": "南京", "latitude": 32.0617, "longitude": 118.7778}


def weather_data():
    return {
        "current": {"time": 1793606400, "temperature_2m": 18.5, "weather_code": 2, "wind_speed_10m": 6.2},
        "current_units": {"temperature_2m": "°C", "wind_speed_10m": "km/h"},
    }


class Schedule:
    def __init__(self):
        self.current = datetime(2026, 11, 2, tzinfo=UTC)
        self.waiting = asyncio.Queue()
        self.wake = asyncio.Queue()

    def now(self):
        return self.current

    async def sleep(self, seconds):
        self.waiting.put_nowait(seconds)
        await self.wake.get()

    def advance(self, seconds):
        self.current += timedelta(seconds=seconds)
        self.wake.put_nowait(None)


def environment(factory, config):
    registry = bootstrap()
    install_lifecycle_slots(registry)
    register_plugins(registry, [plugin()])
    identity = Id("dev.test:sources/environment")
    registry.register(RegistryEntry(identity, "source", SourceSpec(factory), "test", register_to=SOURCES))
    ctx, hooks = Context(registry), HookConnections(registry)
    clock = factory.keywords.get("now")
    records = WorldRecords(ctx, now=(lambda: clock().timestamp()) if clock else time)
    records.open()
    sources = WorldSources(ctx, hooks, records)
    sources.add(
        identity, source_id="environment/test", config=config, presentation="weather" if "place" in config else "time"
    )
    return ctx, hooks, sources


@pytest.mark.parametrize("config", [{"interval_seconds": 0}, {"interval_seconds": True}, {"unexpected": 1}])
def test_clock_configuration_rejects_invalid_parameters(config):
    with pytest.raises(ValueError):
        TIME_CONFIG.parse(config)


@pytest.mark.parametrize(
    "change",
    [
        {"latitude": 91},
        {"longitude": -181},
        {"place": " "},
        {"interval_seconds": 59},
        {"timeout_seconds": 0},
        {"timeout_seconds": 31},
        {"api_key": "secret"},
    ],
)
def test_weather_configuration_rejects_invalid_parameters(change):
    with pytest.raises(ValueError):
        WEATHER_CONFIG.parse({**LOCATION, **change})


def test_clock_has_no_catch_up_and_stops_without_another_observation():
    async def scenario():
        clock = Schedule()
        ctx, hooks, sources = environment(partial(create_time, now=clock.now, sleep=clock.sleep), {})
        records = sources.records
        assert records.observations() == ()
        await sources.prepare()
        assert records.observations() == ()
        await sources.start()
        assert await clock.waiting.get() == 60
        observed = [records.observations()[0]]
        for seconds in (86400, -86400):
            clock.advance(seconds)
            assert await clock.waiting.get() == 60
            observed.append(records.observations()[0])
        values = records.observations()
        assert len(values) == 1 and values[0].position.sequence == 3
        assert observed[0].payload == observed[2].payload
        assert len({value.message_id for value in observed}) == 3
        await sources.stop()
        clock.advance(60)
        await asyncio.sleep(0)
        await sources.clean()
        assert records.observations() == values
        sources.records.close()
        hooks.close()
        ctx.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("failure", ["http", "network", "timeout", "json", "shape", "units", "null"])
def test_weather_failure_is_observed_and_next_period_can_recover(failure):
    async def scenario():
        clock, requests = Schedule(), []

        def respond(request):
            requests.append(request)
            assert request.url.host == "api.open-meteo.com"
            assert request.url.params["latitude"] == str(LOCATION["latitude"])
            assert request.url.params["timeformat"] == "unixtime"
            if len(requests) == 1:
                if failure == "http":
                    return httpx.Response(503)
                if failure == "network":
                    raise httpx.ConnectError("secret-response")
                if failure == "timeout":
                    raise httpx.ReadTimeout("secret-response")
                if failure == "json":
                    return httpx.Response(200, text="secret-response")
                if failure == "shape":
                    return httpx.Response(200, json=[])
                value = weather_data()
                if failure == "units":
                    value["current_units"] = []
                else:
                    value["current"]["temperature_2m"] = None
                return httpx.Response(200, json=value)
            return httpx.Response(200, json=weather_data())

        transport = httpx.MockTransport(respond)
        factory = partial(create_weather, now=clock.now, sleep=clock.sleep, transport=transport)
        ctx, hooks, sources = environment(factory, LOCATION)
        await sources.prepare()
        assert requests == []
        await sources.start()
        assert await clock.waiting.get() == 900
        first = sources.records.observations()[0]
        assert isinstance(first.payload, dict)
        assert first.payload["status"] == "unavailable"
        assert "temperature_c" not in first.payload and "secret-response" not in str(first.payload)
        assert len(requests) == 1
        clock.advance(900)
        assert await clock.waiting.get() == 900
        second = sources.records.observations()[1]
        assert isinstance(second.payload, dict)
        assert second.payload["status"] == "available"
        assert second.payload["place"] == "南京" and second.payload["condition"] == "多云"
        assert second.payload["temperature_c"] == 18.5 and second.payload["wind_kmh"] == 6.2
        assert second.message_id != first.message_id
        await sources.stop()
        await sources.clean()
        sources.records.close()
        hooks.close()
        ctx.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("timeout", [False, True])
def test_pending_weather_request_is_bounded_and_cancelled_before_transport_close(timeout):
    async def scenario():
        clock, events, entered = Schedule(), [], asyncio.Event()

        async def respond(request):
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                events.append("request.finished")
            raise AssertionError("不能到达")

        class Transport(httpx.MockTransport):
            async def aclose(self):
                events.append("transport.closed")
                await super().aclose()

        ctx, hooks, sources = environment(
            partial(create_weather, sleep=clock.sleep, transport=Transport(respond)),
            {**LOCATION, "timeout_seconds": 0.02 if timeout else 10},
        )
        await sources.prepare()
        await sources.start()
        await entered.wait()
        if timeout:
            assert await clock.waiting.get() == 900
            assert cast(dict, sources.records.observations()[0].payload)["error"] == "timeout"
        await sources.stop()
        await sources.clean()
        assert events == ["request.finished", "transport.closed"]
        if not timeout:
            assert sources.records.observations() == ()
        sources.records.close()
        hooks.close()
        ctx.close()

    asyncio.run(scenario())


def test_weather_keeps_four_samples_within_one_hour_and_prunes_on_prepare():
    async def scenario():
        clock = Schedule()
        factory = partial(
            create_weather,
            now=clock.now,
            sleep=clock.sleep,
            transport=httpx.MockTransport(lambda request: httpx.Response(200, json=weather_data())),
        )
        ctx, hooks, sources = environment(factory, LOCATION)
        records = sources.records
        clock.current -= timedelta(hours=2)
        records.append(
            source_id="environment/test",
            message_id="old",
            payload={
                "observed_at": clock.current.isoformat(),
                "status": "unavailable",
            },
        )
        clock.current += timedelta(hours=2)
        await sources.prepare()
        assert records.observations() == ()
        await sources.start()
        await clock.waiting.get()
        for _ in range(4):
            clock.advance(900)
            await clock.waiting.get()
        retained = records.observations()
        assert len(retained) == 4
        assert [record.position.sequence for record in retained] == [3, 4, 5, 6]
        assert [cast(dict, record.payload)["observed_at"] for record in retained] == [
            (clock.current - timedelta(seconds=seconds)).isoformat() for seconds in (2700, 1800, 900, 0)
        ]
        clock.advance(3600)
        await clock.waiting.get()
        assert len(records.observations()) == 1 and records.observations()[0].position.sequence == 7
        await sources.stop()
        await sources.clean()
        sources.records.close()
        hooks.close()
        ctx.close()

    asyncio.run(scenario())


def test_time_updates_expire_weather_without_an_extra_weather_request():
    async def scenario():
        weather_clock, time_clock = Schedule(), Schedule()
        requests = []

        def respond(request):
            requests.append(request)
            return httpx.Response(200, json=weather_data())

        ctx, hooks, sources = environment(
            partial(
                create_weather, now=weather_clock.now, sleep=weather_clock.sleep, transport=httpx.MockTransport(respond)
            ),
            LOCATION,
        )
        identity = Id("dev.test:sources/time")
        ctx.registry.register(
            RegistryEntry(
                identity,
                "source",
                SourceSpec(partial(create_time, now=time_clock.now, sleep=time_clock.sleep)),
                "test",
                register_to=SOURCES,
            )
        )
        sources.add(identity, source_id="time", presentation="time")
        await sources.prepare()
        await sources.start()
        await weather_clock.waiting.get()
        await time_clock.waiting.get()
        weather_clock.current += timedelta(hours=1)
        time_clock.advance(3600)
        await time_clock.waiting.get()
        assert len(requests) == 1
        assert [record.source_id for record in sources.records.observations()] == ["time"]
        await sources.stop()
        await sources.clean()
        sources.records.close()
        hooks.close()
        ctx.close()

    asyncio.run(scenario())
