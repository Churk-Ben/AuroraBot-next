"""通过离线示例进程验证正式默认阶段、持久化及 SIGINT 收尾。"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

APPLICATION = Path(__file__).resolve().parents[2] / "examples" / "react_agent" / "main.py"


def execute(root, *options):
    return subprocess.run(
        [sys.executable, str(APPLICATION), "--data-dir", str(root), *options],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        timeout=15,
    )


def snapshot(root):
    entries = json.loads((root / "framework" / "ctx.json").read_text(encoding="utf-8"))["entries"]
    return {entry["location"]["name"]: entry["value"] for entry in entries}


@pytest.mark.parametrize("mode", ["success", "failure", "timeout"])
def test_default_components_complete_tool_roundtrip_and_restore(tmp_path, mode):
    options = (
        []
        if mode == "success"
        else ["--tool-error"]
        if mode == "failure"
        else ["--tool-delay", "0.2", "--timeout", "0.01"]
    )
    result = execute(tmp_path, "--guide", "保留当前计算进度", *options)
    assert result.returncode == 0, result.stderr
    expected = (
        "计算结果：5" if mode == "success" else "工具反馈：tool_failed" if mode == "failure" else "工具反馈：timeout"
    )
    assert expected in result.stdout and "已接纳新的引导通知" in result.stdout
    state = snapshot(tmp_path)
    assert state["runtime"]["status"] == "completed" and state["progress"] == 2
    assert state["inbox"] == [] and state["context"]["pending"] is None
    messages = state["context"]["messages"]
    assert any(message["role"] == "user" and message["content"] == "保留当前计算进度" for message in messages)
    first_run = state["runtime"]["run_id"]
    result = execute(tmp_path, "--text", "无需行动")
    assert result.returncode == 0, result.stderr
    recovered = snapshot(tmp_path)
    assert recovered["runtime"]["run_id"] != first_run
    assert recovered["context"]["messages"][:-1] == messages
    assert recovered["model_output"]["text"] == "" and recovered["progress"] == 3
    assert len(recovered) == len(state)


def test_sigint_preserves_pending_tools_for_next_activation(tmp_path):
    launcher = """
import asyncio
import runpy
import signal
import sys

source = runpy.run_path(sys.argv[1])
original = source["observe"]

def observe(change):
    original(change)
    if change.action == "set" and isinstance(change.value, dict) and "call" in change.value:
        asyncio.get_running_loop().call_soon(signal.raise_signal, signal.SIGINT)

source["run"].__globals__["observe"] = observe
sys.argv = [sys.argv[1], "--data-dir", sys.argv[2], "--tool-delay", "10", "--timeout", "20"]
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
    state = snapshot(tmp_path)
    assert state["runtime"]["status"] == state["tool_results"]["status"] == "cancelled"
    assert state["context"]["pending"] is not None
    resumed = execute(tmp_path, "--text", "无需行动")
    assert resumed.returncode == 0, resumed.stderr
    recovered = snapshot(tmp_path)
    assert recovered["context"]["pending"] is None and "tool_results" not in recovered
    observations = [
        json.loads(message["content"]) for message in recovered["context"]["messages"] if message["role"] == "tool"
    ]
    assert len(observations) == 1 and observations[0]["status"] == "cancelled"
    assert "工具开始" not in resumed.stdout
