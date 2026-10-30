"""以真实示例进程验证四类控制组件的可见输出和独立运行快照。"""

import json
import os
import subprocess
import sys
from pathlib import Path


def test_control_flow_example_runs_and_retains_each_run(tmp_path):
    application = Path(__file__).resolve().parents[2] / "examples" / "control_flow" / "main.py"
    run_ids = []
    for steps in (3, 4):
        result = subprocess.run(
            [sys.executable, str(application), "--data-dir", str(tmp_path), "--steps", str(steps), "--delay", "0"],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            timeout=15,
        )
        lines = result.stdout.splitlines()
        run_ids.append(next(line.removeprefix("运行 ID: ") for line in lines if line.startswith("运行 ID: ")))
        summary = json.loads(next(line.removeprefix("结果: ") for line in lines if line.startswith("结果: ")))
        assert summary == {"count": steps, "double": steps * 2, "square": steps * steps}
        assert "[控制] root: completed" in lines
        assert any("奇数分支" in line for line in lines)
        assert any("偶数分支" in line for line in lines)
        assert any('[状态] double: {"status": "running"}' == line for line in lines)
        assert any('[状态] square: {"status": "running"}' == line for line in lines)

    assert run_ids[0] != run_ids[1]
    snapshot = json.loads((tmp_path / "framework" / "ctx.json").read_text(encoding="utf-8"))
    summaries = {
        entry["location"]["run_id"]: entry["value"]
        for entry in snapshot["entries"]
        if entry["id"] == "dev.example.control:state/value" and entry["location"]["instance_id"] == "summary"
    }
    assert summaries == {
        run_ids[0]: {"count": 3, "double": 6, "square": 9},
        run_ids[1]: {"count": 4, "double": 8, "square": 16},
    }


def test_control_flow_example_interrupt_persists_cancelled_state(tmp_path):
    application = Path(__file__).resolve().parents[2] / "examples" / "control_flow" / "main.py"
    # 两个计算均启动后发送真实 SIGINT，运行入口仍使用示例自身的 main。
    launcher = """
import asyncio
import runpy
import signal
import sys

source = runpy.run_path(sys.argv[1])
original = source["observe"]

def observe(change):
    original(change)
    if dict(change.address.location)["instance_id"] == "square" and change.value == {"status": "running"}:
        asyncio.get_running_loop().call_soon(signal.raise_signal, signal.SIGINT)

source["main"].__globals__["observe"] = observe
sys.argv = [sys.argv[1], "--data-dir", sys.argv[2], "--steps", "1", "--delay", "0.1"]
source["main"]()
"""
    result = subprocess.run(
        [sys.executable, "-c", launcher, str(application), str(tmp_path)],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        timeout=15,
    )
    assert result.returncode == 130, result.stderr
    assert "[控制] root: cancelled" in result.stdout
    assert "已取消。" in result.stdout
    snapshot = json.loads((tmp_path / "framework" / "ctx.json").read_text(encoding="utf-8"))
    for instance in ("root", "parallel", "double", "square"):
        record = next(entry for entry in snapshot["entries"] if entry["location"]["instance_id"] == instance)
        assert record["value"]["status"] == "cancelled"
    assert not any(entry["location"]["instance_id"] == "summary" for entry in snapshot["entries"])
