"""进程入口、退出码与错误展示。"""

import asyncio
import logging
import sys

from .commander import run_cli


def main() -> int:
    try:
        return asyncio.run(run_cli())
    except KeyboardInterrupt:
        return 130
    except Exception as error:
        if "--debug" in sys.argv[1:]:
            logging.getLogger(__name__).exception("CLI 执行失败")
        else:
            print(f"错误（{type(error).__name__}）：{error}", file=sys.stderr)
        return 1
