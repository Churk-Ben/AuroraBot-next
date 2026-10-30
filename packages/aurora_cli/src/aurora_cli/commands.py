"""命令声明接收与 argv 转换；业务执行目标由公共操作 ID 引用。"""

import argparse
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from aurora_core.bootstrap import REGISTRY_DIRECTORY
from aurora_core.ctx import StateKey
from aurora_core.ids import Id
from aurora_core.json_data import decode_json
from aurora_core.registry import DefinitionRegistry, RegistryEntry

COMMANDS = Id("org.aurora.cli:registries/commands")
CONFIG = Id("org.aurora.cli:state/config")
HELP = Id("org.aurora.cli:commands/help")
WATCH = Id("org.aurora.cli:commands/ctx/watch")
RUN = Id("org.aurora.cli:commands/run")


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


@dataclass(frozen=True)
class Command:
    """CLI 接收方校验后的描述，不要求声明方导入此类型。"""

    id: Id
    help: str
    operation: Id | None
    arguments: tuple[dict[str, Any], ...]


def read_command(entry: RegistryEntry) -> Command:
    if entry.kind != "command" or not isinstance(entry.target, Mapping):
        raise TypeError("命令必须使用 command kind 和映射描述")
    spec = entry.target
    if set(spec) - {"help", "operation", "arguments"} or not isinstance(spec.get("help"), str):
        raise ValueError("命令描述须包含 help，仅支持 help、operation、arguments")
    operation = Id(spec["operation"]) if "operation" in spec else None
    if operation is None and entry.id not in (HELP, WATCH, RUN):
        raise ValueError("扩展命令必须声明 operation 完整 ID")
    arguments = spec.get("arguments", [])
    if not isinstance(arguments, (list, tuple)):
        raise TypeError("命令 arguments 必须为列表或元组")
    names = set()
    for argument in arguments:
        if not isinstance(argument, dict) or set(argument) - {"name", "type", "option", "required"}:
            raise ValueError("参数仅支持 name、type、option、required")
        name = argument.get("name")
        if (
            not isinstance(name, str)
            or not name.isidentifier()
            or not name.isascii()
            or name in names
            or name == "help"
        ):
            raise ValueError("参数名称须为不重复的 ASCII 标识符，且不能为 help")
        names.add(name)
        if argument.get("type", "string") not in _TYPES:
            raise ValueError(f"不支持的参数类型：{argument.get('type')}")
        if any(key in argument and type(argument[key]) is not bool for key in ("option", "required")):
            raise TypeError("option 和 required 必须为布尔值")
        if not argument.get("option", False) and argument.get("required", True) is False:
            raise ValueError("可选参数须使用 option=true")
    return Command(entry.id, spec["help"], operation, tuple(deepcopy(arguments)))


class CommandReceiver:
    def rejection_reason(self, entry: RegistryEntry) -> str | None:
        try:
            read_command(entry)
        except (TypeError, ValueError) as error:
            return str(error)
        return None


def command_parser(command: Command) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=f"aurora {command.id}", description=command.help)
    for argument in command.arguments:
        name = argument["name"]
        option = argument.get("option", False)
        kwargs: dict[str, Any] = {"type": _TYPES[argument.get("type", "string")]}
        if option:
            kwargs.update(dest=name, required=argument.get("required", False), default=argparse.SUPPRESS)
        parser.add_argument(f"--{name.replace('_', '-')}" if option else name, **kwargs)
    return parser


def install_commands(registry: DefinitionRegistry) -> None:
    """登记命令接收方、描述格式、配置状态及内置命令。"""
    key = {"name": "key", "type": "id"}
    optional_key = {**key, "option": True}
    where = {"name": "location", "type": "location", "option": True}
    definitions = {
        "help": {"help": "列出当前可用命令"},
        "ctx/get": {"help": "读取精确状态地址", "arguments": [key, where]},
        "ctx/set": {"help": "以 JSON 整项替换状态", "arguments": [key, {"name": "value", "type": "json"}, where]},
        "ctx/delete": {"help": "删除精确状态地址", "arguments": [key, where]},
        "ctx/list": {"help": "枚举已赋值地址", "arguments": [optional_key, where]},
        "ctx/watch": {"help": "观察当前宿主后续变化，Ctrl+C 退出", "arguments": [optional_key, where]},
        "run": {"help": "启动选定装配，Ctrl+C 停止", "arguments": [{"name": "assembly", "type": "id"}]},
    }
    entries = [
        RegistryEntry(COMMANDS, "registry", CommandReceiver(), "aurora_cli", register_to=REGISTRY_DIRECTORY),
        RegistryEntry(
            Id("org.aurora.cli:schemas/command"),
            "schema",
            {"help": "string", "operation": "完整操作 ID", "arguments": "name/type/option/required 参数列表"},
            "aurora_cli",
            register_to=Id("org.aurora.core:registries/schemas"),
        ),
        RegistryEntry(
            CONFIG, "state_key", StateKey(), "aurora_cli", register_to=Id("org.aurora.core:registries/state_keys")
        ),
    ]
    for name, spec in definitions.items():
        if name in {"ctx/get", "ctx/set", "ctx/delete", "ctx/list"}:
            spec["operation"] = f"org.aurora.core:operations/{name}"
        entries.append(
            RegistryEntry(Id(f"org.aurora.cli:commands/{name}"), "command", spec, "aurora_cli", register_to=COMMANDS)
        )
    registry.register_many(entries)
