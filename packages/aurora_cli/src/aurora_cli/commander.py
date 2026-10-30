"""发现命令、选择入口，并分派至项目工具或运行期宿主。"""

import sys
from collections.abc import Iterable
from typing import TextIO

from aurora_core.admission import AdmissionStatus, inspect_admissions
from aurora_core.bootstrap import bootstrap
from aurora_core.discovery import Plugin, load_plugins, register_plugins
from aurora_core.lifecycle import install_lifecycle_slots

from . import host
from .commands import about, check, donk, help, install_commands
from .declarations import COMMANDS, HELP, RUN, read_command
from .parsing import command_parser, root_parser


async def run_cli(
    argv: list[str] | None = None, *, plugins: Iterable[Plugin] = (), output: TextIO | None = None
) -> int:
    output = sys.stdout if output is None else output
    if output is None:
        raise RuntimeError("标准输出不可用，请显式提供 output 文本流")
    parser = root_parser()
    options = parser.parse_args(argv)
    registry = bootstrap()
    install_commands(registry)
    install_lifecycle_slots(registry)
    register_plugins(registry, load_plugins(explicit=plugins, enabled=options.plugin))
    accepted = {
        admission.source
        for admission in inspect_admissions(registry)
        if admission.target == COMMANDS and admission.status == AdmissionStatus.ACCEPTED
    }
    commands = {entry.id: read_command(entry) for entry in registry.view(register_to=COMMANDS) if entry.id in accepted}
    if options.show_help:
        print(parser.format_help(), file=output)
        help.execute(commands.values(), output)
        return 0
    name, arguments = options.command, options.arguments
    while ":" not in name:
        group = [
            item
            for item in commands.values()
            if item.id.namespace == options.namespace and item.id.local_path.startswith(f"{name}/")
        ]
        if not group:
            break
        if not arguments or arguments[0] in ("--help", "-h"):
            help.execute(group, output)
            return 0
        name, arguments = f"{name}/{arguments[0]}", arguments[1:]
    try:
        entry = registry.resolve(name, namespace=options.namespace, domain="commands")
        command = commands[entry.id]
    except (ValueError, KeyError) as error:
        parser.error(f"命令不可用：{name}（{error}）")
    values = vars(command_parser(command).parse_args(arguments))
    if command.id == HELP:
        help.execute(commands.values(), output)
        return 0
    local = command.id.local_path if command.id.namespace == "org.aurora.cli" else ""
    if local in ("about", "check") or local.startswith("donk/"):
        if options.config is not None or options.assembly is not None:
            parser.error("--config 和 --assembly 仅适用于运行期宿主命令")
        root = options.root.resolve()
        if local == "about":
            return about.execute(root, output)
        if local == "check":
            return check.execute(root, output, **values)
        return donk.execute(local.split("/")[1], root, output)
    if options.data_dir is None:
        parser.error("执行宿主命令必须指定 --data-dir")
    assembly = options.assembly
    if command.id == RUN:
        if assembly is not None:
            parser.error("run 的装配参数与 --assembly 不能同时使用")
        assembly = values["assembly"]
    await host.execute(
        registry, command, values, data_dir=options.data_dir, assembly=assembly, config=options.config, output=output
    )
    return 0
