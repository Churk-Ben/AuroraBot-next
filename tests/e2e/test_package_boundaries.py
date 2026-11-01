"""验证执行包的独立加载、插件发现与兼容类型身份。"""

import json
import os
import subprocess
import sys
from importlib import import_module, metadata
from pathlib import Path


def test_control_runs_without_agent_bot_or_model_packages(tmp_path):
    launcher = """
import importlib.abc
import runpy
import sys

blocked = {'aurora_agent', 'aurora_bot', 'aurora_model_adapter', 'aurora_cli', 'aurora_api'}

class AbsentPackages(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in blocked:
            raise ModuleNotFoundError('独立控制环境不提供：' + fullname)

sys.meta_path.insert(0, AbsentPackages())
from aurora_core.discovery import load_plugins
plugins = load_plugins(enabled=['aurora_bot.control'])
assert plugins[0].entries[0].provider == 'aurora_control'
source = sys.argv.pop(1)
runpy.run_path(source, run_name='__main__')
assert not blocked.intersection(name.split('.')[0] for name in sys.modules)
"""
    example = Path(__file__).resolve().parents[2] / "examples" / "control_flow" / "main.py"
    result = subprocess.run(
        [sys.executable, "-c", launcher, str(example), "--data-dir", str(tmp_path), "--delay", "0"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert '"status": "completed"' in (tmp_path / "framework" / "ctx.json").read_text(encoding="utf-8")


def test_control_distribution_and_compatibility_share_one_implementation():
    import aurora_bot.control as compatibility
    import aurora_control
    from aurora_bot.control import components, execution

    assert metadata.requires("aurora-control") == ["aurora-core>=0.1.0"]
    for name in aurora_control.__all__:
        assert getattr(compatibility, name) is getattr(aurora_control, name)
    assert components.Serial is aurora_control.Serial
    assert execution.ExecutionPlug is aurora_control.ExecutionPlug
    entries = [
        point for point in metadata.entry_points(group="aurorabot.plugins") if point.name == "aurora_bot.control"
    ]
    assert len(entries) == 1
    assert entries[0].value == "aurora_control:plugin"


def test_agent_roundtrip_and_restore_without_bot_or_hosts(tmp_path):
    launcher = """
import importlib.abc
import runpy
import sys

blocked = {'aurora_bot', 'aurora_cli', 'aurora_api'}

class AbsentPackages(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in blocked:
            raise ModuleNotFoundError('独立 agent 环境不提供：' + fullname)

sys.meta_path.insert(0, AbsentPackages())
from aurora_agent.runtime import AgentRuntime
from aurora_core.discovery import load_plugins
plugins = load_plugins(enabled=[
    'aurora_bot.model', 'aurora_bot.react', 'aurora_bot.tools', 'aurora_bot.react_defaults',
])
assert all(entry.provider == 'aurora_agent' for plugin in plugins for entry in plugin.entries)
source = sys.argv.pop(1)
runpy.run_path(source, run_name='__main__')
assert not blocked.intersection(name.split('.')[0] for name in sys.modules)
"""
    example = Path(__file__).resolve().parents[2] / "examples" / "react_agent" / "main.py"
    states = []
    for options in (["--guide", "保持计算进度"], ["--text", "无需行动"]):
        result = subprocess.run(
            [sys.executable, "-c", launcher, str(example), "--data-dir", str(tmp_path), *options],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            timeout=15,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        entries = json.loads((tmp_path / "framework" / "ctx.json").read_text(encoding="utf-8"))["entries"]
        states.append({entry["location"]["name"]: entry["value"] for entry in entries})
    first, restored = states
    assert first["runtime"]["status"] == restored["runtime"]["status"] == "completed"
    assert first["progress"] == 2 and restored["progress"] == 3
    assert restored["context"]["messages"][:-1] == first["context"]["messages"]
    assert any(message["role"] == "tool" for message in first["context"]["messages"])


def test_agent_distribution_and_compatibility_share_one_implementation():
    requirements = metadata.requires("aurora-agent")
    assert requirements is not None
    assert not any(requirement.startswith(("aurora-bot", "aurora-cli", "aurora-api")) for requirement in requirements)
    entries = metadata.entry_points(group="aurorabot.plugins")
    for module in ("react", "react_defaults", "model", "tools"):
        implementation = import_module(f"aurora_agent.{module}")
        compatibility = import_module(f"aurora_bot.{module}")
        for name in compatibility.__all__:
            assert getattr(compatibility, name) is getattr(implementation, name)
        matches = [point for point in entries if point.name == f"aurora_bot.{module}"]
        assert len(matches) == 1
        assert matches[0].value == f"aurora_agent.{module}:plugin"
    runtime = import_module("aurora_agent.runtime")
    compatibility = import_module("aurora_bot.runtime")
    assert issubclass(compatibility.BotRuntime, runtime.AgentRuntime)
    for name in ("RunHandle", "RunResult", "Submission"):
        assert getattr(compatibility, name) is getattr(runtime, name)
