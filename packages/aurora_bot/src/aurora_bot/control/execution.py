"""控制组件的兼容导入入口；类型与实现由 aurora_control 提供。"""

from aurora_control.execution import (
    CONTROL_STATE,
    ExecutionLink,
    ExecutionPlug,
    ExecutionRequest,
    ExecutionSlot,
    InstanceStateBinding,
    StateBinding,
    component_entries,
    execution_slot_entry,
)

__all__ = [
    "CONTROL_STATE",
    "ExecutionLink",
    "ExecutionPlug",
    "ExecutionRequest",
    "ExecutionSlot",
    "InstanceStateBinding",
    "StateBinding",
    "component_entries",
    "execution_slot_entry",
]
