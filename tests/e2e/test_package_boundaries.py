"""验证执行包的独立加载、插件发现与兼容类型身份。"""

import os
import subprocess
import sys
from importlib import metadata
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
