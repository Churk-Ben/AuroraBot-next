"""命令行解析与参数转换。"""

import argparse
from pathlib import Path
from typing import Any

from aurora_core.ids import Id
from aurora_core.json_data import decode_json

from .declarations import Command


def json_object(content: str) -> dict[str, Any]:
    value = decode_json(content)
    if not isinstance(value, dict):
        raise TypeError("必须提供 JSON 对象")
    return value


def location(content: str) -> dict[str, str]:
    value = json_object(content)
    if any(not key or not isinstance(item, str) or not item for key, item in value.items()):
        raise ValueError("业务定位字段和值必须为非空字符串")
    return value


_TYPES = {"string": str, "integer": int, "json": decode_json, "id": Id, "location": location}


def command_parser(command: Command) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(allow_abbrev=False, prog=f"aurora {command.id}", description=command.help)
    for argument in command.arguments:
        name = argument["name"]
        option = argument.get("option", False)
        kwargs: dict[str, Any] = (
            {"action": "store_true"}
            if argument.get("type") == "flag"
            else {"type": _TYPES[argument.get("type", "string")]}
        )
        if option:
            kwargs.update(dest=name, required=argument.get("required", False), default=argparse.SUPPRESS)
        parser.add_argument(f"--{name.replace('_', '-')}" if option else name, **kwargs)
    return parser


def root_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        allow_abbrev=False, prog="aurora", description="AuroraBot 当前进程宿主与命令入口", add_help=False
    )
    parser.add_argument("-h", "--help", action="store_true", dest="show_help", help="查看命令帮助")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="命令使用的项目根目录")
    parser.add_argument("--debug", action="store_true", help="显示完整异常信息")
    parser.add_argument("--data-dir", type=Path, help="宿主独占的数据目录；执行命令时必填")
    parser.add_argument("--plugin", action="append", default=[], help="启用 aurorabot.plugins 入口，可重复")
    parser.add_argument("--namespace", default="org.aurora.cli", help="交互短名的命名空间")
    parser.add_argument("--assembly", type=Id, help="命令运行期间启动的装配完整 ID")
    parser.add_argument("--config", type=json_object, help="恢复后、prepare 前写入 CLI 配置状态的 JSON 对象")
    parser.add_argument("command", nargs="?", help="完整命令 ID 或当前命名空间中的路径")
    parser.add_argument("arguments", nargs=argparse.REMAINDER, help="命令参数；全局选项须放在命令前")
    return parser
