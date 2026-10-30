"""跨进程验证插件发现、watch 中断、关闭故障及最终快照恢复。"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("fault", ["", "stop", "flush"])
def test_real_cli_interrupt_and_shutdown_status(tmp_path, fault):
    metadata = tmp_path / "m1_fixture-0.0.0.dist-info"
    metadata.mkdir()
    (metadata / "METADATA").write_text("Metadata-Version: 2.1\nName: m1-fixture\nVersion: 0.0.0\n")
    (metadata / "entry_points.txt").write_text("[aurorabot.plugins]\nm1_fixture = m1_cli_plugin:plugin\n")
    env = dict(os.environ)
    fixtures = Path(__file__).resolve().parents[1] / "fixtures"
    env["PYTHONPATH"] = os.pathsep.join([str(tmp_path), str(fixtures)])
    env["PYTHONIOENCODING"] = "utf-8"
    env["AURORA_M1_FAULT"] = fault
    data = tmp_path / "data"

    def run(*args):
        return subprocess.run(
            [sys.executable, "-m", "aurora_cli", "--plugin", "m1_fixture", "--data-dir", str(data), *args],
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
            timeout=15,
        )

    initial = run("ctx/set", "dev.m1:state/value", '"baseline"')
    assert initial.returncode == 0, initial.stderr
    snapshot = data / "framework" / "ctx.json"
    before = snapshot.read_bytes()
    result = run("--assembly", "dev.m1:assemblies/watch", "ctx/watch", "--key", "dev.m1:state/value")
    assert result.returncode == (1 if fault else 130), result.stderr
    events = [json.loads(line) for line in result.stdout.splitlines()]
    assert [event["value"] for event in events] == ["first", "second"]
    assert [event["revision"] for event in events] == [1, 2]
    if fault:
        assert "故障" in result.stderr
    if fault == "flush":
        assert snapshot.read_bytes() == before
    if not fault:
        trace = (data / "namespaces" / "ns-dev.m1" / "events.txt").read_text(encoding="utf-8").splitlines()
        assert trace == ["first", "second", "gate:closed", "stopped", "source:closed"]
        restored = run("ctx/get", "dev.m1:state/value")
        assert restored.returncode == 0, restored.stderr
        assert json.loads(restored.stdout) == "stopped"
