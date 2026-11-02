"""使用已有配置启动 bot API，由 Python 构造 JSON 参数以避开 shell 转义。"""

import argparse
import json
import sys
from pathlib import Path

from aurora_bot.assembly_config import AGENTS, MESSAGES, RUN, WORK
from aurora_bot.conversation import CONVERSATION
from aurora_cli.main import main as cli_main


def main() -> int:
    parser = argparse.ArgumentParser(description="使用已有 TOML 配置启动本机 bot API，供 TUI 连接")
    parser.add_argument("--data-dir", type=Path, default=Path("data"), help="宿主数据目录，默认 data")
    parser.add_argument("--port", type=int, default=10270, help="本机端口，默认 10270")
    args = parser.parse_args()
    sys.argv = [
        "aurora",
        "--data-dir",
        str(args.data_dir),
        "serve",
        "--port",
        str(args.port),
        "--keys",
        json.dumps([str(key) for key in (AGENTS, MESSAGES, RUN, WORK)]),
        "--endpoints",
        json.dumps([str(CONVERSATION)]),
    ]
    return cli_main()


if __name__ == "__main__":
    raise SystemExit(main())
