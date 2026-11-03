"""时间与 Open-Meteo 天气观察；周期只写入 world，不激活 agent。"""

import asyncio
import math
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

import httpx
from aurora_config import ConfigSchema
from aurora_core import Id
from aurora_core.discovery import Plugin
from aurora_core.registry import RegistryEntry

from .sources import SOURCES, SourceEmit, SourceInstance, SourceSpec

TIME = Id("org.aurora.world:sources/environment/time")
WEATHER = Id("org.aurora.world:sources/environment/weather")
_CONDITIONS = {
    0: "晴",
    1: "大部晴朗",
    2: "多云",
    3: "阴",
    45: "雾",
    48: "雾凇",
    51: "小毛毛雨",
    53: "中等毛毛雨",
    55: "强毛毛雨",
    56: "轻微冻毛毛雨",
    57: "强冻毛毛雨",
    61: "小雨",
    63: "中雨",
    65: "大雨",
    66: "轻微冻雨",
    67: "强冻雨",
    71: "小雪",
    73: "中雪",
    75: "大雪",
    77: "米雪",
    80: "小阵雨",
    81: "中等阵雨",
    82: "强阵雨",
    85: "小阵雪",
    86: "强阵雪",
    95: "雷暴",
    96: "雷暴伴小冰雹",
    99: "雷暴伴强冰雹",
}
TIME_CONFIG = ConfigSchema(
    {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "interval_seconds": {"type": "number", "minimum": 1, "maximum": 86400, "default": 60},
        },
    }
)
WEATHER_CONFIG = ConfigSchema(
    {
        "type": "object",
        "additionalProperties": False,
        "required": ["place", "latitude", "longitude"],
        "properties": {
            "place": {"type": "string", "pattern": r"\S"},
            "latitude": {"type": "number", "minimum": -90, "maximum": 90},
            "longitude": {"type": "number", "minimum": -180, "maximum": 180},
            "interval_seconds": {"type": "number", "minimum": 60, "maximum": 86400, "default": 900},
            "timeout_seconds": {"type": "number", "exclusiveMinimum": 0, "maximum": 30, "default": 10},
        },
    }
)


def _now() -> datetime:
    return datetime.now().astimezone()


async def _noop() -> None:
    pass


def _periodic(
    emit: SourceEmit,
    observe: Callable[[], Awaitable[dict[str, object]]],
    interval: float,
    sleep: Callable[[float], Awaitable[None]],
    *,
    aclose: Callable[[], Awaitable[None]] = _noop,
) -> SourceInstance:
    session = uuid4().hex

    async def run() -> None:
        sequence = 0
        while True:
            payload = await observe()
            sequence += 1
            emit(message_id=f"{session}/{sequence}", payload=payload)
            await sleep(interval)

    return SourceInstance(_noop, _noop, aclose, run)


async def create_time(
    *,
    source_id: str,
    emit: SourceEmit,
    config: dict[str, object],
    now: Callable[[], datetime] = _now,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> SourceInstance:
    """每次采样记录宿主本地时间；使用相对等待，不补发错过的周期。"""
    values = cast(dict, TIME_CONFIG.parse(config))

    async def observe() -> dict[str, object]:
        current = now()
        return {"kind": "time", "observed_at": current.isoformat(), "timezone": current.tzname()}

    return _periodic(emit, observe, values["interval_seconds"], sleep)


def _current_weather(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or not isinstance(value.get("current"), dict):
        raise TypeError("天气响应缺少 current")
    current = value["current"]
    fields = ("time", "temperature_2m", "weather_code", "wind_speed_10m")
    if any(type(current.get(key)) not in (int, float) or not math.isfinite(current[key]) for key in fields):
        raise ValueError("天气响应数值无效")
    if type(current["weather_code"]) is not int or not 0 <= current["weather_code"] <= 99:
        raise ValueError("天气代码无效")
    units = value.get("current_units")
    if not isinstance(units, dict) or units.get("temperature_2m") != "°C" or units.get("wind_speed_10m") != "km/h":
        raise ValueError("天气响应单位不匹配")
    try:
        valid_at = datetime.fromtimestamp(current["time"], UTC).isoformat()
    except (ValueError, OverflowError, OSError):
        raise ValueError("天气响应时间无效") from None
    return {
        "valid_at": valid_at,
        "temperature_c": current["temperature_2m"],
        "weather_code": current["weather_code"],
        "condition": _CONDITIONS.get(current["weather_code"], "未知天气代码"),
        "wind_kmh": current["wind_speed_10m"],
    }


async def create_weather(
    *,
    source_id: str,
    emit: SourceEmit,
    config: dict[str, object],
    now: Callable[[], datetime] = _now,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    transport: httpx.AsyncBaseTransport | None = None,
) -> SourceInstance:
    """有界请求当前天气；失败形成明确观察，下个周期再采样，不重试本次请求。"""
    values = cast(dict, WEATHER_CONFIG.parse(config))
    client = httpx.AsyncClient(transport=transport, timeout=values["timeout_seconds"], follow_redirects=False)

    async def observe() -> dict[str, object]:
        payload: dict[str, object] = {
            "kind": "weather",
            "observed_at": now().isoformat(),
            "place": values["place"],
            "latitude": values["latitude"],
            "longitude": values["longitude"],
            "provider": "Open-Meteo",
            "attribution": "https://open-meteo.com/",
        }
        try:
            async with asyncio.timeout(values["timeout_seconds"]):
                response = await client.get(
                    "https://api.open-meteo.com/v1/forecast",
                    params={
                        "latitude": values["latitude"],
                        "longitude": values["longitude"],
                        "current": "temperature_2m,weather_code,wind_speed_10m",
                        "temperature_unit": "celsius",
                        "wind_speed_unit": "kmh",
                        "timeformat": "unixtime",
                    },
                )
                response.raise_for_status()
                weather = _current_weather(response.json())
        except (httpx.TimeoutException, TimeoutError):
            error = "timeout"
        except httpx.HTTPStatusError:
            error = "http_error"
        except httpx.RequestError:
            error = "unavailable"
        except (ValueError, TypeError):
            error = "invalid_response"
        else:
            return {**payload, "status": "available", **weather}
        return {**payload, "status": "unavailable", "error": error}

    return _periodic(
        emit,
        observe,
        values["interval_seconds"],
        sleep,
        aclose=client.aclose,
    )


def plugin() -> Plugin:
    """仅登记来源工厂；HTTP 客户端在 prepare 创建，网络访问在 run 内执行。"""
    return Plugin(
        "aurora_world.environment",
        (
            RegistryEntry(TIME, "source", SourceSpec(create_time), "aurora_world.environment", register_to=SOURCES),
            RegistryEntry(
                WEATHER, "source", SourceSpec(create_weather), "aurora_world.environment", register_to=SOURCES
            ),
        ),
        requires=("aurora_world",),
    )
