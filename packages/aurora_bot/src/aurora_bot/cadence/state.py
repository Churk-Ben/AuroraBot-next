"""cadence 的来源选择、持久消费位置和转交关联。"""

from typing import cast

from aurora_config import ConfigSchema
from aurora_core import Id
from aurora_core.json_data import encode_json
from aurora_world import WorldPosition

CONFIGURATION = Id("org.aurora.bot:configs/cadence")
CONFIG_STATE = Id("org.aurora.bot:state/cadence_config")
CHECKPOINT = Id("org.aurora.bot:state/cadence")


def _identity(value: object) -> None:
    if type(value) is not str or not value.strip():
        raise ValueError("cadence 身份必须为非空字符串")


def _sources(value: object) -> None:
    sources = cast(dict, value)["source_ids"]
    for source in sources:
        _identity(source)
    if len(sources) != len(set(sources)):
        raise ValueError("cadence 来源身份不能重复")


CADENCE_CONFIG = ConfigSchema(
    {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "source_ids": {"type": "array", "items": {"type": "string"}, "default": []},
        },
    },
    check=_sources,
)


def position(value: object) -> WorldPosition | None:
    """从持久数据恢复完整锚点，不接受只有序号的游标。"""
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {"journal_id", "sequence", "record_id"}:
        raise ValueError("cadence 消费位置无效")
    return WorldPosition(**value)


def _transfer(value: object) -> WorldPosition:
    if not isinstance(value, dict) or set(value) != {"position", "source_id", "message_id", "payload"}:
        raise ValueError("cadence 转交消息无效")
    anchor = position(value["position"])
    if anchor is None or anchor.sequence == 0:
        raise ValueError("cadence 转交须绑定世界记录")
    _identity(value["source_id"])
    _identity(value["message_id"])
    return anchor


def validate_checkpoint(value: object) -> None:
    """同时校验消费顺序和关联身份；配置和运行句柄不进入快照。"""
    encode_json(value)
    if not isinstance(value, dict) or set(value) != {
        "version",
        "source_ids",
        "position",
        "pending",
        "receipts",
        "error",
    }:
        raise ValueError("cadence 消费状态无效")
    if type(value["version"]) is not int or value["version"] != 1:
        raise ValueError("不支持的 cadence 消费状态版本")
    CADENCE_CONFIG.validate({"source_ids": value["source_ids"]})
    cursor = position(value["position"])
    if value["error"] not in (
        None,
        "TransferUncertain",
        "CursorInvalid",
        "SelectionChanged",
        "RuntimeBusy",
        "ForwarderFailed",
    ):
        raise ValueError("cadence 暂停原因无效")
    if value["pending"] is not None:
        pending = _transfer(value["pending"])
        if cursor is not None and (pending.journal_id != cursor.journal_id or pending.sequence <= cursor.sequence):
            raise ValueError("待转交消息必须晚于消费位置")
        if value["pending"]["source_id"] not in value["source_ids"]:
            raise ValueError("待转交消息不属于所选来源")
    if not isinstance(value["receipts"], list):
        raise TypeError("cadence 回执必须为列表")
    previous_world = previous_guidance = 0
    identities = set()
    for receipt in value["receipts"]:
        if not isinstance(receipt, dict) or set(receipt) != {"message", "guidance_id", "sequence", "run_id"}:
            raise ValueError("cadence 回执结构无效")
        anchor = _transfer(receipt["message"])
        if (
            cursor is None
            or anchor.journal_id != cursor.journal_id
            or not previous_world < anchor.sequence <= cursor.sequence
            or (anchor.sequence == cursor.sequence and anchor != cursor)
            or receipt["message"]["source_id"] not in value["source_ids"]
        ):
            raise ValueError("cadence 回执与消费位置不一致")
        _identity(receipt["guidance_id"])
        _identity(receipt["run_id"])
        if receipt["guidance_id"] in identities:
            raise ValueError("cadence 引导身份重复")
        if type(receipt["sequence"]) is not int or receipt["sequence"] <= previous_guidance:
            raise ValueError("cadence 引导序号必须递增")
        identities.add(receipt["guidance_id"])
        previous_world, previous_guidance = anchor.sequence, receipt["sequence"]
