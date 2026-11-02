"""world 插件发现入口；只登记持久记录定义，不创建来源或后台任务。"""

from aurora_core.ctx import StateKey
from aurora_core.discovery import Plugin
from aurora_core.registry import RegistryEntry

from .records import RECORDS, validate_records


def plugin() -> Plugin:
    """提供可显式启用的插件清单。"""
    return Plugin(
        "aurora_world",
        (RegistryEntry(RECORDS, "state_key", StateKey(validate_records), "aurora_world"),),
    )
