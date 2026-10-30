"""启动本机 ctx API，等待取消并释放连接。"""

import asyncio
import logging

from aurora_core.ids import Id

from ...declarations import CONFIG, CommandContext, command_plugin


async def dispatch(context: CommandContext, port: int = 10270, keys: object = None) -> None:
    """默认仅开放 CLI 配置状态；keys 显式指定允许读写和订阅的完整键列表。"""
    from aurora_api.server import serve

    if keys is None:
        allowed = [CONFIG]
    elif isinstance(keys, list) and all(isinstance(key, str) for key in keys):
        allowed = [Id(key) for key in keys]
    else:
        raise ValueError("--keys 须为完整状态 ID 的 JSON 数组")
    async with serve(context.registry, keys=allowed, port=port) as url:
        logging.getLogger(__name__).info("ctx API 已监听 %s，Ctrl+C 停止", url)
        await asyncio.Event().wait()


def plugin():
    return command_plugin(
        __name__,
        {
            "serve": {
                "help": "启动本机 ctx API；默认端口 10270，keys 为开放状态 ID 的 JSON 数组（默认 CLI config）",
                "executor": dispatch,
                "runtime": True,
                "arguments": [
                    {"name": "port", "type": "integer", "option": True},
                    {"name": "keys", "type": "json", "option": True},
                ],
            }
        },
    )
