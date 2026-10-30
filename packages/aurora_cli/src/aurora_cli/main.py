"""当前进程内的 CLI 宿主，显式加载插件并通过 core 执行。"""

import argparse
import asyncio
import inspect
import logging
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import TextIO

from aurora_core.admission import AdmissionStatus, inspect_admissions
from aurora_core.bootstrap import bootstrap
from aurora_core.ctx import StateAddress, StateChange, install_context
from aurora_core.discovery import Plugin, load_plugins, register_plugins
from aurora_core.hooks import HookConnections
from aurora_core.ids import Id
from aurora_core.invocation import invoke_operation
from aurora_core.json_data import encode_json
from aurora_core.lifecycle import Lifecycle, LifecycleComponent, install_lifecycle_slots
from aurora_core.persistence import ContextPersistence
from aurora_core.registry import DefinitionRegistry
from aurora_core.storage import StorageService

from .commands import COMMANDS, CONFIG, HELP, RUN, WATCH, command_parser, install_commands, json_object, read_command


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aurora", description="AuroraBot 当前进程宿主与命令入口")
    parser.add_argument("--data-dir", type=Path, help="宿主独占的数据目录；执行命令时必填")
    parser.add_argument("--plugin", action="append", default=[], help="启用 aurorabot.plugins 入口，可重复")
    parser.add_argument("--namespace", default="org.aurora.cli", help="交互短名的命名空间")
    parser.add_argument("--assembly", type=Id, help="命令运行期间启动的装配完整 ID")
    parser.add_argument("--config", type=json_object, help="恢复后、prepare 前写入 CLI 配置状态的 JSON 对象")
    parser.add_argument("command", nargs="?", default="help", help="完整命令 ID 或当前命名空间中的路径")
    parser.add_argument("arguments", nargs=argparse.REMAINDER, help="命令参数；全局选项须放在命令前")
    return parser


def _address(address: StateAddress) -> dict[str, object]:
    return {"id": str(address.key), "location": dict(address.location)}


def _write(output: TextIO, value: object) -> None:
    print(encode_json(value), file=output, flush=True)


async def watch(registry: DefinitionRegistry, output: TextIO, **filters: object) -> None:
    """订阅当前宿主中的后续变化；取消或输出失败时释放订阅。"""
    changes: asyncio.Queue[StateChange] = asyncio.Queue()
    handle = await invoke_operation(
        registry, Id("org.aurora.core:operations/ctx/subscribe"), changes.put_nowait, **filters
    )
    try:
        while True:
            change = await changes.get()
            _write(
                output,
                {
                    **_address(change.address),
                    "revision": change.revision,
                    "action": change.action,
                    "value": change.value,
                    "previous": change.previous,
                    "existed": change.existed,
                },
            )
    finally:
        await invoke_operation(registry, Id("org.aurora.core:operations/ctx/unsubscribe"), handle)


async def run_cli(
    argv: list[str] | None = None, *, plugins: Iterable[Plugin] = (), output: TextIO | None = None
) -> None:
    """装配工厂同步接收 registry/ctx/hooks/storage，返回 LifecycleComponent 可迭代对象。

    工厂只负责定义和连接；资源初始化与任务启动放在 prepare/start，以便生命周期清理。
    可注入显式插件清单，命令行插件仅通过已安装且显式启用的 entry point 加载。
    """
    output = sys.stdout if output is None else output
    parser = _parser()
    options = parser.parse_args(argv)
    registry = bootstrap()
    install_commands(registry)
    install_lifecycle_slots(registry)
    ctx = install_context(registry)
    lifecycle: Lifecycle | None = None
    try:
        register_plugins(registry, load_plugins(explicit=plugins, enabled=options.plugin))
        accepted = {
            admission.source
            for admission in inspect_admissions(registry)
            if admission.target == COMMANDS and admission.status == AdmissionStatus.ACCEPTED
        }
        commands = {
            entry.id: read_command(entry) for entry in registry.view(register_to=COMMANDS) if entry.id in accepted
        }
        name = options.command
        arguments = options.arguments
        if name == "ctx" and (not arguments or arguments[0] in ("--help", "-h")):
            for item in commands.values():
                if item.id.namespace == options.namespace and item.id.local_path.startswith("ctx/"):
                    print(f"{item.id}  {item.help}", file=output)
            return
        if name == "ctx":
            name = f"ctx/{arguments[0]}"
            arguments = arguments[1:]
        entry = registry.resolve(name, namespace=options.namespace, domain="commands")
        if entry.id not in commands:
            raise ValueError(f"目标未被 CLI 命令表接收：{entry.id}")
        command = commands[entry.id]
        values = vars(command_parser(command).parse_args(arguments))
        if command.id == HELP:
            for item in commands.values():
                print(f"{item.id}  {item.help}", file=output)
            return
        if options.data_dir is None:
            parser.error("执行命令必须指定 --data-dir")
        assembly = options.assembly
        if command.id == RUN:
            if assembly is not None:
                parser.error("run 的装配参数与 --assembly 不能同时使用")
            assembly = values["assembly"]
        factory = None
        if assembly is not None:
            assembly_entry = registry.get(assembly)
            if assembly_entry.kind != "assembly" or not callable(assembly_entry.target):
                raise TypeError(f"装配必须为可调用的 assembly：{assembly}")
            factory = assembly_entry.target

        storage = StorageService(options.data_dir)
        hooks = HookConnections(registry)
        try:
            components = () if factory is None else factory(registry=registry, ctx=ctx, hooks=hooks, storage=storage)
            if inspect.iscoroutine(components):
                components.close()
                raise TypeError("装配工厂必须同步返回组件")
            if not isinstance(components, Iterable):
                raise TypeError("装配工厂必须返回 LifecycleComponent 可迭代对象")
            components = tuple(components)
            if any(not isinstance(component, LifecycleComponent) for component in components):
                raise TypeError("装配包含无效组件")
            lifecycle = Lifecycle(
                ctx,
                hooks,
                components,
                persistence=ContextPersistence(ctx, storage.snapshot_store()),
                storage=storage,
            )
        except BaseException:
            hooks.close()
            storage.close()
            raise

        def configure() -> None:
            if options.config is not None:
                ctx.set(CONFIG, options.config)

        await lifecycle.start(configure=configure)
        try:
            if command.id == RUN:
                await lifecycle.run(asyncio.Event().wait)
            elif command.id == WATCH:
                await lifecycle.run(watch, registry, output, **values)
            else:
                if command.operation is None:
                    raise ValueError("命令没有执行目标")
                result = await lifecycle.run(invoke_operation, registry, command.operation, **values)
                if command.id == Id("org.aurora.cli:commands/ctx/list"):
                    if not isinstance(result, tuple) or any(not isinstance(item, StateAddress) for item in result):
                        raise TypeError("ctx/list 必须返回状态地址元组")
                    result = [_address(item) for item in result]
                _write(output, result)
        finally:
            await lifecycle.stop()
    finally:
        # 生命周期拥有运行期状态；解析或装配失败时由入口释放尚未交接的 ctx。
        if lifecycle is None:
            ctx.close()


def main() -> int:
    try:
        asyncio.run(run_cli())
    except KeyboardInterrupt:
        return 130
    except Exception:
        logging.getLogger(__name__).exception("CLI 执行失败")
        return 1
    return 0
