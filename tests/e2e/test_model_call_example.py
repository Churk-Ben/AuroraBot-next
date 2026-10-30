"""通过示例进程验证流式模型状态、部分输出保留和最终快照。"""

import json
import os
import subprocess
import sys
from pathlib import Path

APPLICATION = Path(__file__).resolve().parents[2] / "examples" / "model_call" / "main.py"


def output_state(root):
    snapshot = json.loads((root / "framework" / "ctx.json").read_text(encoding="utf-8"))
    assert len(snapshot["entries"]) == 1
    record = snapshot["entries"][0]
    assert record["id"] == "dev.example.model:state/output"
    return record["value"]


def test_example_retains_latest_response_or_partial_failure(tmp_path):
    for options in ([], ["--no-stream"], ["--fail"]):
        result = subprocess.run(
            [sys.executable, str(APPLICATION), "--data-dir", str(tmp_path), "--delay", "0", *options],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            timeout=15,
        )
        failed = "--fail" in options
        assert result.returncode == (1 if failed else 0), result.stderr
        assert "假模型收到：你好" in result.stdout
        value = output_state(tmp_path)
        assert value["status"] == ("failed" if failed else "completed")
        assert value["text"] == ("假模型收到：你好" if failed else "假模型收到：你好。")
        assert value["finish_reason"] == (None if failed else "stop")
        assert value["tool_calls"] == []


def test_example_sigint_keeps_received_text(tmp_path):
    launcher = """
import asyncio
import runpy
import signal
import sys

source = runpy.run_path(sys.argv[1])
original = source["observe"]

def observe(change):
    original(change)
    if change.action == "set" and change.value["status"] == "running" and change.value["text"] == "假模型收到：":
        asyncio.get_running_loop().call_soon(signal.raise_signal, signal.SIGINT)

source["main"].__globals__["observe"] = observe
sys.argv = [sys.argv[1], "--data-dir", sys.argv[2], "--delay", "0.1"]
source["main"]()
"""
    result = subprocess.run(
        [sys.executable, "-c", launcher, str(APPLICATION), str(tmp_path)],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        timeout=15,
    )
    assert result.returncode == 130, result.stderr
    assert "状态: cancelled" in result.stdout
    value = output_state(tmp_path)
    assert value["status"] == "cancelled"
    assert value["text"] == "假模型收到："
    assert value["finish_reason"] is None
