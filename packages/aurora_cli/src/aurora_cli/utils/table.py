"""以 Rich 渲染中文和多行单元格，不解析内容中的样式标记。"""

from collections.abc import Sequence
from io import StringIO
from typing import TextIO

from rich import box
from rich.console import Console
from rich.table import Table
from rich.text import Text


def make_table(headers: Sequence[str], rows: Sequence[Sequence[str]], *, banner: Sequence[str] | None = None) -> Table:
    if not headers:
        raise ValueError("表格至少需要一列")
    content = [*([banner] if banner is not None else []), *rows]
    if any(len(row) != len(headers) for row in content):
        raise ValueError("每行与 banner 的列数必须与 headers 一致")
    table = Table(box=box.ASCII, show_lines=True, header_style="bold cyan", safe_box=True, show_header=banner is None)
    for header in headers:
        table.add_column(Text(header), overflow="fold")
    if banner is not None:
        table.add_row(*(Text(cell) for cell in banner))
        table.add_row(*(Text(header, style="bold cyan") for header in headers))
    for row in rows:
        table.add_row(*(Text(cell) for cell in row))
    return table


def print_table(headers: Sequence[str], rows: Sequence[Sequence[str]], *, output: TextIO) -> None:
    Console(file=output).print(make_table(headers, rows))


def render_table(
    headers: Sequence[str], rows: Sequence[Sequence[str]], *, banner: Sequence[str] | None = None, width: int = 100
) -> str:
    """返回可测试、无 ANSI 控制码的文本表格。"""
    output = StringIO()
    Console(file=output, width=width, force_terminal=False, color_system=None).print(
        make_table(headers, rows, banner=banner)
    )
    return output.getvalue().rstrip("\n")
