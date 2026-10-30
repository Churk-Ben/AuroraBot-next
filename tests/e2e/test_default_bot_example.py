"""跨进程验证默认装配的身份、上下文和模型绑定恢复。"""

import json
import os
import subprocess
import sys
from pathlib import Path

APPLICATION = Path(__file__).resolve().parents[2] / "examples" / "default_bot" / "main.py"


def invoke(root, *options):
    result = subprocess.run(
        [sys.executable, str(APPLICATION), "--data-dir", str(root), *options],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_default_assembly_restores_configuration_and_waits_for_explicit_activation(tmp_path):
    idle = invoke(tmp_path)
    assert "装配已启动；尚未激活" in idle and "内部输出" not in idle
    first = invoke(tmp_path, "--text", "你好")
    assert "内部输出: 模型一:回显:你好" in first
    switched = invoke(tmp_path, "--profile", "secondary", "--text", "再次见面")
    assert "内部输出: 模型二:回显:再次见面" in switched
    repeated = invoke(tmp_path, "--text", "第三次")
    assert "创建模型: 模型二" in repeated and "内部输出: 模型二:回显:第三次" in repeated
    snapshot = json.loads((tmp_path / "framework" / "ctx.json").read_text(encoding="utf-8"))
    records = snapshot["entries"]
    context = next(record["value"] for record in records if record["id"] == "org.aurora.bot:state/messages")
    assert [message["content"] for message in context["messages"] if message["role"] == "user"] == [
        "你好",
        "再次见面",
        "第三次",
    ]
    assert context["guidance_sequence"] == 3 and context["pending"] is None
    work = [record for record in records if record["id"] == "org.aurora.bot:state/react_work"]
    assert len(work) == 1 and work[0]["location"]["part"] == "model_output"
