"""显示当前接收的命令及其完整身份。"""

from collections.abc import Iterable
from typing import TextIO

from rich.console import Console
from rich.table import Table
from rich.text import Text

from ...declarations import Command

DEFINITIONS = {"help": {"help": "列出当前可用命令"}}


def execute(commands: Iterable[Command], output: TextIO) -> None:
    table = Table("命令 ID", "用途")
    for item in commands:
        table.add_row(Text(str(item.id)), Text(item.help))
    Console(file=output).print(table)
