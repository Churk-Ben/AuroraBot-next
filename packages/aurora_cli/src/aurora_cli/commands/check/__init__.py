"""将代码质量检查交给工作区的 TypeScript 脚本。"""

from pathlib import Path
from typing import TextIO

from ...utils.process import run_process

FLAGS = ("lint", "test", "coverage", "fix", "unsafe_fixes", "check")
DEFINITIONS = {
    "check": {
        "help": "运行质量检查；可选择 lint、test、coverage 或显式修复",
        "arguments": [{"name": name, "type": "flag", "option": True} for name in FLAGS],
    }
}


def execute(root: Path, output: TextIO, **options: object) -> int:
    if not (root / "scripts" / "check.ts").is_file() or not (root / "package.json").is_file():
        raise ValueError("项目根目录缺少 scripts/check.ts 或 package.json，请指定 --root")
    flags = [f"--{name.replace('_', '-')}" for name in FLAGS if options.get(name)]
    return run_process(["pnpm", "run", "check", *flags], root=root, output=output)
