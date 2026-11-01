"""在禁止导入 CLI/API 的独立进程中验收默认 bot。"""

import os
import subprocess
import sys
from pathlib import Path


def test_default_bot_runs_when_cli_and_api_imports_are_unavailable(tmp_path):
    launcher = """
import importlib.abc
import runpy
import sys

class AbsentHosts(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'aurora_cli', 'aurora_api'}:
            raise ModuleNotFoundError('验收环境未安装可选宿主：' + fullname)

sys.meta_path.insert(0, AbsentHosts())
source = sys.argv.pop(1)
from pathlib import Path
sys.path.insert(0, str(Path(source).parent))
runpy.run_path(source, run_name='__main__')
assert not any(name.split('.')[0] in {'aurora_cli', 'aurora_api'} for name in sys.modules)
"""
    example = Path(__file__).resolve().parents[2] / "examples" / "default_bot" / "main.py"
    result = subprocess.run(
        [sys.executable, "-c", launcher, str(example), "--data-dir", str(tmp_path), "--text", "隔离验收"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "内部输出: 模型一:回显:隔离验收" in result.stdout
    assert (tmp_path / "framework" / "ctx.json").is_file()
