"""运行工作区 Python 检查：uv run python scripts/check.py。"""

import subprocess
import sys
from pathlib import Path


def main() -> None:
    """在仓库根目录依次检查格式、静态规则与行为。"""
    root = Path(__file__).resolve().parents[1]
    for arguments in (("ruff", "check", "."), ("ruff", "format", "--check", "."), ("pytest",)):
        subprocess.run([sys.executable, "-m", *arguments], cwd=root, check=True)


if __name__ == "__main__":
    main()
