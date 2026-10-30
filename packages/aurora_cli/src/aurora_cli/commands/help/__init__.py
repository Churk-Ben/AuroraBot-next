"""显示当前接收的命令及其完整身份。"""

from collections.abc import Iterable
from typing import TextIO

from ...declarations import Command
from ...utils.table import print_table

DEFINITIONS = {"help": {"help": "列出当前可用命令"}}


def execute(commands: Iterable[Command], output: TextIO) -> None:
    print_table(("命令 ID", "用途"), [(str(item.id), item.help) for item in commands], output=output)
