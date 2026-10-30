"""发现命令、选择入口，并分派至项目工具或运行期宿主。"""

import logging
import sys
from collections.abc import Iterable
from importlib.metadata import version
from typing import TextIO

from aurora_core.admission import AdmissionStatus, inspect_admissions
from aurora_core.bootstrap import bootstrap
from aurora_core.discovery import Plugin, load_plugins, register_plugins
from aurora_core.lifecycle import install_lifecycle_slots
from aurora_logging import configure_logging

from . import host
from .commands import discover_commands, install_commands
from .declarations import COMMANDS, CommandContext, read_command
from .execution import execute_command
from .parsing import parse_command, root_parser
from .presentation import show_commands


async def run_cli(
    argv: list[str] | None = None, *, plugins: Iterable[Plugin] = (), output: TextIO | None = None
) -> int:
    output = sys.stdout if output is None else output
    if output is None:
        raise RuntimeError("标准输出不可用，请显式提供 output 文本流")
    parser = root_parser()
    options = parser.parse_args(argv)
    if options.command[:1] == ["--"]:
        options.command = options.command[1:]
    if options.version:
        print(f"aurora {version('aurora-cli')}", file=output)
        return 0
    console_level = logging.DEBUG if options.debug else logging.INFO
    configure_logging(console_level=console_level, console_tracebacks=options.debug)
    registry = bootstrap()
    install_commands(registry)
    install_lifecycle_slots(registry)
    register_plugins(registry, load_plugins(explicit=(*discover_commands(), *plugins), enabled=options.plugin))
    accepted = {
        admission.source
        for admission in inspect_admissions(registry)
        if admission.target == COMMANDS and admission.status == AdmissionStatus.ACCEPTED
    }
    commands = {entry.id: read_command(entry) for entry in registry.view(register_to=COMMANDS) if entry.id in accepted}
    if options.show_help or not options.command:
        if options.show_help:
            print(parser.format_help(), file=output)
        show_commands(commands.values(), output)
        return 0
    name, arguments = options.command[0], options.command[1:]
    while ":" not in name:
        group = [
            item
            for item in commands.values()
            if item.id.namespace == options.namespace and item.id.local_path.startswith(f"{name}/")
        ]
        if not group:
            break
        if not arguments or arguments[0] in ("--help", "-h"):
            show_commands(group, output)
            return 0
        name, arguments = f"{name}/{arguments[0]}", arguments[1:]
    try:
        entry = registry.resolve(name, namespace=options.namespace, domain="commands")
        command = commands[entry.id]
    except (ValueError, KeyError) as error:
        parser.error(f"命令不可用：{name}（{error}）")
    values = parse_command(command, arguments)
    context = CommandContext(options.root.resolve(), output, registry, tuple(commands.values()))
    if not command.runtime:
        if options.config is not None or options.assembly is not None:
            parser.error("--config 和 --assembly 仅适用于运行期宿主命令")
        return await execute_command(command, context, values)
    if options.data_dir is None:
        parser.error("执行宿主命令必须指定 --data-dir")
    assembly = options.assembly
    if command.assembly_argument is not None:
        selected = values.pop(command.assembly_argument, None)
        if selected is not None:
            if assembly is not None:
                parser.error("命令的装配参数与 --assembly 不能同时使用")
            assembly = selected
    configure_logging(
        log_dir=options.data_dir.resolve() / "logs",
        console_level=console_level,
        console_tracebacks=options.debug,
    )
    return await host.execute(
        context, command, values, data_dir=options.data_dir, assembly=assembly, config=options.config
    )
