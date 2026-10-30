"""内置控制插件：显式连接实例，以 ctx 共享业务数据。"""

from aurora_core.ctx import StateKey
from aurora_core.discovery import Plugin
from aurora_core.hooks import HookSlot
from aurora_core.ids import Id
from aurora_core.registry import RegistryEntry

from .components import Branch, Controller, LoopLimitExceeded, Parallel, Serial, While
from .execution import (
    CHILDREN,
    CONTROL_STATE,
    EXECUTE,
    ExecutionLink,
    ExecutionPlug,
    ExecutionRequest,
    ExecutionSlot,
    StateBinding,
)


def plugin() -> Plugin:
    """仅声明当前使用的控制端口和调用状态；实例与地址由装配提供。"""
    return Plugin(
        "aurora_bot.control",
        (
            RegistryEntry(
                CHILDREN,
                "hook_slot",
                HookSlot(lambda entry: None if isinstance(entry.target, ExecutionPlug) else "需要绑定执行插头实例"),
                "aurora_bot",
                register_to=Id("org.aurora.core:registries/hook_slots"),
            ),
            RegistryEntry(
                EXECUTE,
                "hook_handler",
                ExecutionPlug.__call__,
                "aurora_bot",
                register_to=Id("org.aurora.core:registries/hook_handlers"),
            ),
            RegistryEntry(
                CONTROL_STATE,
                "state_key",
                StateKey(),
                "aurora_bot",
                register_to=Id("org.aurora.core:registries/state_keys"),
            ),
        ),
    )


__all__ = [
    "CHILDREN",
    "CONTROL_STATE",
    "EXECUTE",
    "Branch",
    "Controller",
    "ExecutionLink",
    "ExecutionPlug",
    "ExecutionRequest",
    "ExecutionSlot",
    "LoopLimitExceeded",
    "Parallel",
    "Serial",
    "StateBinding",
    "While",
    "plugin",
]
