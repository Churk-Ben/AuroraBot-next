"""验证执行包的独立加载、插件发现与命名空间归属。"""

import json
import os
import subprocess
import sys
from importlib import import_module, metadata
from pathlib import Path

import pytest
from aurora_core.discovery import ENTRY_POINT_GROUP, load_plugins


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
plugins = load_plugins(enabled=['aurora_control'])
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


def test_control_distribution_owns_its_plugin_and_definitions():
    assert metadata.requires("aurora-control") == ["aurora-core>=0.1.0"]
    entries = [point for point in metadata.entry_points(group=ENTRY_POINT_GROUP) if point.name == "aurora_control"]
    assert len(entries) == 1
    assert entries[0].value == "aurora_control:plugin"
    plugin = load_plugins(enabled=["aurora_control"])[0]
    assert len(plugin.entries) == 16
    assert all(
        entry.id.namespace == "org.aurora.control" and entry.provider == "aurora_control" for entry in plugin.entries
    )


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
    'aurora_agent.model', 'aurora_agent.react', 'aurora_agent.tools', 'aurora_agent.react_defaults',
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


def test_agent_distribution_owns_its_plugins_and_definitions():
    requirements = metadata.requires("aurora-agent")
    assert requirements is not None
    assert not any(requirement.startswith(("aurora-bot", "aurora-cli", "aurora-api")) for requirement in requirements)
    entries = metadata.entry_points(group=ENTRY_POINT_GROUP)
    names = []
    for module in ("react", "react_defaults", "model", "tools"):
        names.append(f"aurora_agent.{module}")
        matches = [point for point in entries if point.name == names[-1]]
        assert len(matches) == 1
        assert matches[0].value == f"aurora_agent.{module}:plugin"
    plugins = load_plugins(enabled=names)
    assert all(
        entry.id.namespace == "org.aurora.agent" and entry.provider == "aurora_agent"
        for plugin in plugins
        for entry in plugin.entries
    )


@pytest.mark.parametrize("module", ["control", "model", "react", "react_defaults", "tools", "runtime"])
def test_bot_does_not_export_execution_components(module):
    with pytest.raises(ModuleNotFoundError):
        import_module(f"aurora_bot.{module}")
    with pytest.raises(ValueError, match="匹配数：0"):
        load_plugins(enabled=[f"aurora_bot.{module}"])


def test_workspace_plugins_use_the_aurora_discovery_group():
    for name in ("aurora-agent", "aurora-control", "aurora-bot", "aurora-model-adapter", "aurora-world"):
        points = metadata.distribution(name).entry_points
        assert points and all(point.group == "aurora.plugins" for point in points)
