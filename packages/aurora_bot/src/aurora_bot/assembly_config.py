"""默认单 bot 装配的可恢复配置及显式状态地址。"""

import math
from typing import TypedDict, cast

from aurora_core.ids import Id
from aurora_core.json_data import encode_json
from aurora_model_adapter import JsonValue

CONFIG = Id("org.aurora.bot:state/config")
AGENTS = Id("org.aurora.bot:state/agents")
MESSAGES = Id("org.aurora.bot:state/messages")
RUN = Id("org.aurora.bot:state/run")
WORK = Id("org.aurora.bot:state/react_work")


class ToolSelection(TypedDict):
    tool: str
    instance_id: str
    config: dict[str, JsonValue]


class BotConfig(TypedDict):
    instance_id: str
    model_role: str
    tools: list[ToolSelection]
    max_iterations: int
    tool_timeout: float
    streaming: bool
    system_prompt: str


def validate_json(value: object) -> None:
    encode_json(value)


def parse_config(value: object) -> BotConfig:
    """补齐运行参数默认值，拒绝未知字段；不改写已保存配置。"""
    encode_json(value)
    if not isinstance(value, dict):
        raise TypeError("bot 配置必须为对象")
    fields = {"instance_id", "model_role", "tools", "max_iterations", "tool_timeout", "streaming", "system_prompt"}
    if value.keys() - fields or any(
        not isinstance(value.get(key), str) or not value[key] for key in ("instance_id", "model_role")
    ):
        raise ValueError("bot 配置需要 instance_id/model_role，且不得包含未知字段")
    iterations, timeout = value.get("max_iterations", 8), value.get("tool_timeout", 30.0)
    if type(iterations) is not int or iterations < 1:
        raise ValueError("max_iterations 必须为正整数")
    if type(timeout) not in (float, int) or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("tool_timeout 必须为正有限数")
    if type(value.get("streaming", True)) is not bool or not isinstance(value.get("system_prompt", ""), str):
        raise ValueError("streaming 必须为布尔值，system_prompt 必须为字符串")
    selections = value.get("tools", [])
    if not isinstance(selections, list):
        raise TypeError("tools 必须为工具选择列表")
    tools: list[ToolSelection] = []
    instances: set[str] = set()
    for item in selections:
        if (
            not isinstance(item, dict)
            or item.keys() - {"tool", "instance_id", "config"}
            or any(not isinstance(item.get(key), str) or not item[key] for key in ("tool", "instance_id"))
            or not isinstance(item.get("config", {}), dict)
        ):
            raise ValueError("工具选择需要 tool/instance_id 及可选 config 对象")
        Id(item["tool"])
        if item["instance_id"] in instances:
            raise ValueError("工具实例身份重复")
        instances.add(item["instance_id"])
        tools.append({"tool": item["tool"], "instance_id": item["instance_id"], "config": item.get("config", {})})
    return cast(
        BotConfig,
        {
            "instance_id": value["instance_id"],
            "model_role": value["model_role"],
            "tools": tools,
            "max_iterations": iterations,
            "tool_timeout": timeout,
            "streaming": value.get("streaming", True),
            "system_prompt": value.get("system_prompt", ""),
        },
    )


def validate_config(value: object) -> None:
    parse_config(value)
