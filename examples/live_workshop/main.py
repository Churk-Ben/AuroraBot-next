"""持续巡检工作台入口；复用 CLI 的命令解析、宿主、日志与 API。"""

import asyncio
import logging
import sys

from aurora_cli.commander import run_cli
from aurora_cli.parsing import root_parser
from aurora_core.json_data import encode_json
from demo import ASSEMBLY, EXPOSED, plugins


async def run(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    options = root_parser().parse_args(argv)
    if options.connect is None:
        if not options.command and not options.show_help and not options.version:
            argv += ["serve"]
            options.command = ["serve"]
        if options.command[:1] == ["serve"]:
            boundary = len(argv) - len(options.command)
            argv = [
                "--assembly",
                str(ASSEMBLY),
                *argv[:boundary],
                "serve",
                "--keys",
                encode_json([str(key) for key in EXPOSED]),
                *options.command[1:],
            ]
        argv = ["--data-dir", "build/live-workshop", *argv]
    return await run_cli(argv, plugins=plugins())


def main():
    try:
        return asyncio.run(run())
    except KeyboardInterrupt:
        return 130
    except Exception:
        logging.getLogger(__name__).exception("持续巡检工作台执行失败")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
