"""world 插件发现入口；世界来源和状态定义由具体功能提供。"""

from aurora_core.discovery import Plugin


def plugin() -> Plugin:
    """提供可显式启用的插件清单。"""
    return Plugin("aurora_world")
