"""控制组件的兼容导入入口；类型与实现由 aurora_control 提供。"""

from aurora_control import (
    CONTROL_STATE,
    Branch,
    Controller,
    ExecutionLink,
    ExecutionPlug,
    ExecutionRequest,
    ExecutionSlot,
    InstanceStateBinding,
    LoopLimitExceeded,
    Parallel,
    Serial,
    StateBinding,
    While,
    component_entries,
    execution_slot_entry,
    plugin,
)

__all__ = [
    "CONTROL_STATE",
    "Branch",
    "Controller",
    "ExecutionLink",
    "ExecutionPlug",
    "ExecutionRequest",
    "ExecutionSlot",
    "InstanceStateBinding",
    "LoopLimitExceeded",
    "Parallel",
    "Serial",
    "StateBinding",
    "While",
    "component_entries",
    "execution_slot_entry",
    "plugin",
]
