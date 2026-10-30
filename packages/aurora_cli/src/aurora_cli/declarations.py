"""命令声明接收与 argv 转换；业务执行目标由公共操作 ID 引用。"""

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from aurora_core.ids import Id
from aurora_core.registry import RegistryEntry

COMMANDS = Id("org.aurora.cli:registries/commands")
CONFIG = Id("org.aurora.cli:state/config")
HELP = Id("org.aurora.cli:commands/help")
WATCH = Id("org.aurora.cli:commands/ctx/watch")
RUN = Id("org.aurora.cli:commands/run")


ARGUMENT_TYPES = frozenset({"string", "integer", "json", "id", "location", "flag"})
LOCAL_COMMANDS = frozenset(
    Id(f"org.aurora.cli:commands/{name}")
    for name in ("help", "ctx/watch", "run", "about", "check", "donk/show", "donk/major", "donk/minor", "donk/patch")
)


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
    if operation is None and entry.id not in LOCAL_COMMANDS:
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
        if argument.get("type", "string") not in ARGUMENT_TYPES:
            raise ValueError(f"不支持的参数类型：{argument.get('type')}")
        if any(key in argument and type(argument[key]) is not bool for key in ("option", "required")):
            raise TypeError("option 和 required 必须为布尔值")
        if not argument.get("option", False) and argument.get("required", True) is False:
            raise ValueError("可选参数须使用 option=true")
        if argument.get("type") == "flag" and not argument.get("option", False):
            raise ValueError("flag 类型仅支持命名选项")
    return Command(entry.id, spec["help"], operation, tuple(deepcopy(arguments)))


class CommandReceiver:
    def rejection_reason(self, entry: RegistryEntry) -> str | None:
        try:
            read_command(entry)
        except (TypeError, ValueError) as error:
            return str(error)
        return None
