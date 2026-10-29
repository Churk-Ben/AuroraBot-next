"""以独立进程验证 core 外应用的首次运行、恢复与业务地址区分。"""

import subprocess
import sys
from pathlib import Path


def test_counter_runs_and_restores_across_processes(tmp_path):
    application = Path(__file__).resolve().parents[2] / "examples" / "core_counter.py"

    def run(name, amount):
        result = subprocess.run(
            [sys.executable, str(application), "--data-dir", str(tmp_path), "--name", name, "--amount", str(amount)],
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        )
        return result.stdout.strip()

    assert run("first", 2) == "first: 2"
    assert run("first", 3) == "first: 5"
    assert run("second", 1) == "second: 1"
    assert run("first", -1) == "first: 4"
    assert (tmp_path / "framework" / "ctx.json").is_file()
