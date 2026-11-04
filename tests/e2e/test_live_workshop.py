"""跨进程验证常驻示例的 CLI、bot 循环、控制组件和关闭恢复。"""

import asyncio
import json
import os
import re
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from aurora_api.client import CtxClient

EXAMPLE = Path(__file__).resolve().parents[2] / "examples" / "live_workshop" / "main.py"
PREFIX = "dev.example.workshop:state/"
LAUNCHER = """
import asyncio
import runpy
import signal
import sys
from pathlib import Path

source_path, stop_path, *arguments = sys.argv[1:]
sys.path.insert(0, str(Path(source_path).parent))
source = runpy.run_path(source_path)
original = source['run']

async def interrupt():
    while not Path(stop_path).exists():
        await asyncio.sleep(0.02)
    signal.raise_signal(signal.SIGINT)

async def run():
    monitor = asyncio.create_task(interrupt())
    try:
        return await original()
    finally:
        monitor.cancel()
        await asyncio.gather(monitor, return_exceptions=True)

source['main'].__globals__['run'] = run
sys.argv = [source_path, *arguments]
raise SystemExit(source['main']())
"""


@asynccontextmanager
async def workshop(root, initial=None):
    stop = root / "interrupt"
    stop.unlink(missing_ok=True)
    options = [] if initial is None else ["--config", json.dumps(initial)]
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        LAUNCHER,
        str(EXAMPLE),
        str(stop),
        "-d",
        str(root / "data"),
        *options,
        "serve",
        "--port",
        "0",
        env={**os.environ, "PYTHONIOENCODING": "utf-8", "NO_COLOR": "1", "COLUMNS": "180"},
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    assert process.stderr is not None
    drain = None
    startup = []
    try:
        async with asyncio.timeout(10):
            while True:
                line = await process.stderr.readline()
                if not line:
                    raise AssertionError(b"".join(startup).decode("utf-8"))
                startup.append(line)
                match = re.search(rb"http://127\.0\.0\.1:\d+", line)
                if match:
                    break
        drain = asyncio.create_task(process.stderr.read())
        async with CtxClient(match.group().decode()) as client:
            yield client, process, stop
        stop.touch()
        await asyncio.wait_for(process.wait(), 8)
        errors = (await drain).decode("utf-8")
        assert process.returncode == 130, errors
        assert "Task exception was never retrieved" not in errors
        assert "生命周期停止失败" not in errors
    finally:
        if process.returncode is None:
            process.kill()
        await process.wait()
        if drain is not None:
            await drain


async def state(client, key, **filters):
    value = await client.request("get", key=key, **filters)
    assert isinstance(value, dict)
    return value


async def until(client, key, predicate, **filters):
    async with asyncio.timeout(20):
        while True:
            value = await state(client, key, **filters)
            if predicate(value):
                return value
            await asyncio.sleep(0.03)


async def cli_set(client, key, value):
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "aurora_cli",
        "--connect",
        client.url,
        "ctx",
        "set",
        key,
        json.dumps(value),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    output, error = await asyncio.wait_for(process.communicate(), 10)
    assert process.returncode == 0, error.decode("utf-8")
    assert json.loads(output) is None


def test_automatic_cycles_controls_pause_and_persistent_reports(tmp_path):
    async def scenario():
        async with workshop(tmp_path, {"interval": 0.5, "delay": 0}) as (client, process, _):
            async with client.watch(key="org.aurora.control:state/control") as events:
                seen = set()

                async def collect():
                    async for event in events:
                        if event["action"] == "set":
                            seen.add(event["location"]["definition_id"])

                collector = asyncio.create_task(collect())
                try:
                    reports = await until(client, PREFIX + "reports", lambda value: value["total"] >= 2)
                finally:
                    collector.cancel()
                    await asyncio.gather(collector, return_exceptions=True)
            assert process.returncode is None
            assert {
                "org.aurora.control:handlers/control/" + name for name in ("serial", "while", "branch", "parallel")
            } <= seen
            result = reports["recent"][-1]["result"]["value"]
            assert result == {"count": 3, "parity": "odd", "double": 6, "square": 9}
            await cli_set(client, PREFIX + "settings", {"automatic": False, "interval": 0.5, "delay": 0})
            status = await until(client, PREFIX + "status", lambda value: value["status"] == "completed")
            world = await state(client, PREFIX + "world")
            await until(client, PREFIX + "world", lambda value: value["tick"] >= world["tick"] + 2)
            assert (await state(client, PREFIX + "status"))["activations"] == status["activations"]
            assert await client.request("list", key=PREFIX + "pipeline") == []
            total = (await state(client, PREFIX + "reports"))["total"]
            await cli_set(client, "org.aurora.adapter:state/model/bindings", {"reasoning": "fast"})
        (tmp_path / "data/config/org.aurora.adapter/model/bindings.toml").write_text(
            'reasoning = "fast"\n', encoding="utf-8"
        )
        async with workshop(tmp_path) as (client, _, _):
            assert (await state(client, PREFIX + "reports"))["total"] == total
            assert (await state(client, PREFIX + "settings"))["automatic"] is False
            await cli_set(client, PREFIX + "request", {"text": "重启后的手动任务", "steps": 4})
            reports = await until(client, PREFIX + "reports", lambda value: value["total"] == total + 1)
            assert reports["recent"][-1]["result"]["value"]["parity"] == "even"
            await until(client, PREFIX + "status", lambda value: value["status"] == "completed")
            context = await state(client, "org.aurora.bot:state/messages", location={"instance_id": "workshop"})
            assert context["messages"][-1]["content"].startswith("fast")
            assert context["pending"] is None and len(context["messages"]) <= 8
        assert (tmp_path / "data" / "logs" / "aurora.log").exists()

    asyncio.run(scenario())


def test_guidance_during_activation_and_tool_failure_keep_host_running(tmp_path):
    async def scenario():
        async with workshop(tmp_path, {"automatic": False, "delay": 0.2}) as (client, process, _):
            await cli_set(client, PREFIX + "request", {"text": "第一次任务", "steps": 10})
            await until(
                client,
                "org.aurora.bot:state/run",
                lambda value: value.get("phase") == "act",
                location={"instance_id": "workshop"},
            )
            original = await state(client, PREFIX + "status")
            await cli_set(client, PREFIX + "request", {"text": "运行中追加", "steps": 2})
            reports = await until(client, PREFIX + "reports", lambda value: value["total"] == 2)
            status = await until(client, PREFIX + "status", lambda value: value["status"] == "completed")
            assert status["run_id"] == original["run_id"] and status["activations"] == 1
            assert {item["text"] for item in reports["recent"]} == {"第一次任务", "运行中追加"}
            await cli_set(client, PREFIX + "request", {"text": "故障演示", "fail": True})
            reports = await until(client, PREFIX + "reports", lambda value: value["total"] == 3)
            assert reports["recent"][-1]["result"]["error"]["code"] == "tool_failed"
            await until(client, PREFIX + "status", lambda value: value["status"] == "completed")
            await cli_set(client, PREFIX + "request", {"text": "故障后的任务", "steps": 1})
            await until(client, PREFIX + "reports", lambda value: value["total"] == 4)
            assert process.returncode is None

    asyncio.run(scenario())


def test_interrupt_cancels_active_tool_and_restores_pending_observation(tmp_path):
    async def scenario():
        async with workshop(tmp_path, {"automatic": False, "delay": 1}) as (client, _, _):
            await cli_set(client, PREFIX + "request", {"text": "中断任务", "steps": 20})
            await until(
                client,
                "org.aurora.bot:state/run",
                lambda value: value.get("phase") == "act",
                location={"instance_id": "workshop"},
            )
        snapshot = json.loads((tmp_path / "data" / "framework" / "ctx.json").read_text(encoding="utf-8"))
        entries = snapshot["entries"]
        runtime = next(item["value"] for item in entries if item["id"] == "org.aurora.bot:state/run")
        assert runtime["status"] == "cancelled"
        assert not any(item["id"] in (PREFIX + "pipeline", "org.aurora.control:state/control") for item in entries)
        async with workshop(tmp_path) as (client, _, _):
            await cli_set(client, PREFIX + "settings", {"automatic": False, "delay": 0})
            await cli_set(client, PREFIX + "request", {"text": "恢复后的任务", "steps": 1})
            reports = await until(client, PREFIX + "reports", lambda value: value["total"] == 2)
            assert [item["result"]["status"] for item in reports["recent"]] == ["cancelled", "completed"]

    asyncio.run(scenario())
