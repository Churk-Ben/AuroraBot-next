"""启动本机 ctx API，等待取消并释放连接。"""

import asyncio
import logging

from aurora_core.ids import Id

from ...declarations import CONFIG, CommandContext, command_plugin


async def dispatch(
    context: CommandContext,
    port: int = 10270,
    keys: object = None,
    endpoints: object = None,
    read_only_keys: object = None,
) -> None:
    """keys 开放读写和订阅，read_only_keys 仅开放读取和订阅；两者不得重叠。"""
    from aurora_api.server import serve

    if keys is None:
        allowed = [CONFIG]
    elif isinstance(keys, list) and all(isinstance(key, str) for key in keys):
        allowed = [Id(key) for key in keys]
    else:
        raise ValueError("--keys 须为完整状态 ID 的 JSON 数组")
    if read_only_keys is None:
        readonly = []
    elif isinstance(read_only_keys, list) and all(isinstance(key, str) for key in read_only_keys):
        readonly = [Id(key) for key in read_only_keys]
    else:
        raise ValueError("--read-only-keys 须为完整状态 ID 的 JSON 数组")
    if endpoints is None:
        selected = []
    elif isinstance(endpoints, list) and all(isinstance(endpoint, str) for endpoint in endpoints):
        selected = [Id(endpoint) for endpoint in endpoints]
    else:
        raise ValueError("--endpoints 须为产品端点 ID 的 JSON 数组")
    async with serve(context.registry, keys=allowed, read_only_keys=readonly, port=port, endpoints=selected) as url:
        logging.getLogger(__name__).info("ctx API 已监听 %s，Ctrl+C 停止", url)
        await asyncio.Event().wait()


def plugin():
    return command_plugin(
        __name__,
        {
            "serve": {
                "help": "启动本机 API；keys 为开放状态 ID 数组（默认 CLI config），endpoints 为显式开放的产品端点 ID 数组",
                "executor": dispatch,
                "runtime": True,
                "arguments": [
                    {"name": "port", "type": "integer", "option": True},
                    {"name": "keys", "type": "json", "option": True},
                    {"name": "read_only_keys", "type": "json", "option": True},
                    {"name": "endpoints", "type": "json", "option": True},
                ],
            }
        },
    )
