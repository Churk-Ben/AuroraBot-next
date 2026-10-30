"""内置控制插件：显式连接实例，以 ctx 共享业务数据。"""

from aurora_core.ctx import StateKey
from aurora_core.discovery import Plugin
from aurora_core.ids import Id
from aurora_core.registry import RegistryEntry

from .components import Branch, Controller, LoopLimitExceeded, Parallel, Serial, While
from .execution import (
    CONTROL_STATE,
    ExecutionLink,
    ExecutionPlug,
    ExecutionRequest,
    ExecutionSlot,
    StateBinding,
    component_entries,
)


def plugin() -> Plugin:
    """登记控制组件定义、各自的执行与子组件端口，以及在途调用状态。"""
    return Plugin(
        "aurora_bot.control",
        (
            *(
                entry
                for component in (Controller, Serial, Branch, While, Parallel)
                for entry in component_entries(
                    component.definition_id, component, component.execute, provider="aurora_bot", children=True
                )
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
    "CONTROL_STATE",
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
    "component_entries",
    "plugin",
]
