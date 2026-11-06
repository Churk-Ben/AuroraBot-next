"""使用已有配置启动 bot API，由 Python 构造 JSON 参数以避开 shell 转义。"""

import argparse
import json
import sys
from pathlib import Path

from aurora_bot.assembly_config import AGENTS, MESSAGES, RUN, WORK
from aurora_bot.cadence.state import CHECKPOINT
from aurora_bot.conversation import CONVERSATION
from aurora_cli.main import main as cli_main
from aurora_config import CONFIGURATION
from aurora_world import ENVIRONMENT, RECORDS, SOURCE_STATUS


def main() -> int:
    parser = argparse.ArgumentParser(description="使用已有 TOML 配置启动本机 bot API，供 TUI 连接")
    parser.add_argument("--data-dir", type=Path, default=Path("data"), help="宿主数据目录，默认 data")
    parser.add_argument("--port", type=int, default=10270, help="本机端口，默认 10270")
    parser.add_argument("--edit-config", action="store_true", help="开放已登记 TOML 配置编辑，保存后重启生效")
    parser.add_argument("--world", action="store_true", help="开放世界记录和来源状态；须先在宿主启用 world 插件")
    parser.add_argument("--cadence", action="store_true", help="开放消费位置和转交诊断；须先启用 aurora_bot.cadence")
    args = parser.parse_args()
    sys.argv = [
        "aurora",
        "--data-dir",
        str(args.data_dir),
        "serve",
        "--port",
        str(args.port),
        "--keys",
        "[]",
        "--read-only-keys",
        json.dumps(
            [
                str(key)
                for key in (
                    AGENTS,
                    MESSAGES,
                    RUN,
                    WORK,
                    *((RECORDS, ENVIRONMENT, SOURCE_STATUS) if args.world else ()),
                    *((CHECKPOINT,) if args.cadence else ()),
                )
            ]
        ),
        "--endpoints",
        json.dumps([str(CONVERSATION), *([str(CONFIGURATION)] if args.edit_config else [])]),
    ]
    return cli_main()


if __name__ == "__main__":
    raise SystemExit(main())
