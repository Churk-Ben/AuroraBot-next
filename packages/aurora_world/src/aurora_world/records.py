"""单宿主内的世界记录、来源去重和持久读取位置。"""

import json
from copy import deepcopy
from dataclasses import dataclass
from typing import TypedDict, cast
from uuid import uuid4

from aurora_core.ctx import Context
from aurora_core.ids import Id
from aurora_core.json_data import encode_json

RECORDS = Id("org.aurora.world:state/records")


def _identity(value: object) -> None:
    if type(value) is not str or not value.strip():
        raise ValueError("世界记录身份必须为非空字符串")
    encode_json(value)


@dataclass(frozen=True)
class WorldPosition:
    """日志及记录身份共同锚定读取位置；sequence 为 0 时 record_id 必须为空。"""

    journal_id: str
    sequence: int
    record_id: str | None = None

    def __post_init__(self) -> None:
        _identity(self.journal_id)
        if type(self.sequence) is not int or self.sequence < 0:
            raise ValueError("世界读取位置必须为非负整数")
        if self.sequence == 0:
            if self.record_id is not None:
                raise ValueError("日志起点不能绑定记录身份")
        else:
            _identity(self.record_id)


@dataclass(frozen=True)
class WorldRecord:
    """独立数据副本；来源消息、世界记录与读取位置不包含 bot 或运行身份。"""

    position: WorldPosition
    record_id: str
    source_id: str
    message_id: str
    payload: object


@dataclass(frozen=True)
class WorldReceipt:
    """内存接纳结果，不承诺已经落盘，也不表示已向消费者转交。"""

    record: WorldRecord
    duplicate: bool


class MessageConflictError(ValueError):
    """同一来源消息身份已对应不同内容，拒绝覆盖或生成新记录。"""


class CursorError(ValueError):
    """读取位置不属于当前日志或超出已保存范围，须由消费者核对。"""


class _StoredRecord(TypedDict):
    sequence: int
    record_id: str
    source_id: str
    message_id: str
    payload: object


class _Journal(TypedDict):
    version: int
    journal_id: str
    records: list[_StoredRecord]


def validate_records(value: object) -> None:
    """校验完整日志和唯一身份；恢复损坏或不支持的快照时明确拒绝。"""
    encode_json(value)
    if not isinstance(value, dict) or set(value) != {"version", "journal_id", "records"}:
        raise ValueError("世界日志结构无效")
    if type(value["version"]) is not int or value["version"] != 1:
        raise ValueError("不支持的世界日志版本")
    _identity(value["journal_id"])
    records = value["records"]
    if not isinstance(records, list):
        raise TypeError("世界记录必须为列表")
    identities: set[tuple[str, str]] = set()
    record_ids: set[str] = set()
    for sequence, record in enumerate(records, start=1):
        if not isinstance(record, dict) or set(record) != {
            "sequence",
            "record_id",
            "source_id",
            "message_id",
            "payload",
        }:
            raise ValueError("世界记录结构无效")
        if type(record["sequence"]) is not int or record["sequence"] != sequence:
            raise ValueError("世界记录序号必须从 1 连续递增")
        for field in ("record_id", "source_id", "message_id"):
            _identity(record[field])
        identity = (record["source_id"], record["message_id"])
        if identity in identities or record["record_id"] in record_ids:
            raise ValueError("世界记录身份重复")
        identities.add(identity)
        record_ids.add(record["record_id"])


def _record(journal: _Journal, value: _StoredRecord) -> WorldRecord:
    return WorldRecord(
        WorldPosition(journal["journal_id"], value["sequence"], value["record_id"]),
        value["record_id"],
        value["source_id"],
        value["message_id"],
        value["payload"],
    )


def _content(value: object) -> str:
    # JSON 对象键序不影响重复判断；布尔值、整数和浮点数保留各自编码。
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)


class WorldRecords:
    """通过 ctx 的全局 RECORDS 地址接收与读取消息，仅依赖 core。

    append 同步执行，一次 set 提交记录及去重身份，不创建后台资源。来源须提供稳定的
    source_id/message_id；内容只能包含严格 JSON 数据，凭证由来源在写入前排除。
    订阅使用 ctx.subscribe(callback, key=RECORDS, location={})，通知只提示重新读取，
    不承担历史补发；先订阅再 read，并以 WorldPosition 排除重复读取。

    日志随宿主 ContextPersistence 保存，接纳与落盘之间存在崩溃窗口。首版保留全部
    记录，不自动裁剪，不提供删除或重写接口；宿主不得通过通用 ctx 写入破坏日志历史。
    每次操作复制完整日志，适用于首版有限规模输入，不承诺大容量消息存储性能。
    """

    def __init__(self, ctx: Context) -> None:
        self._ctx = ctx

    def _load(self) -> _Journal | None:
        if not self._ctx.list(key=RECORDS, location={}):
            return None
        return cast(_Journal, self._ctx.get(RECORDS))

    def append(self, *, source_id: str, message_id: str, payload: object) -> WorldReceipt:
        """同身份同内容返回原记录且不发布通知；不同内容抛出 MessageConflictError。"""
        _identity(source_id)
        _identity(message_id)
        encode_json(payload)
        journal = self._load()
        if journal is None:
            journal = _Journal(version=1, journal_id=uuid4().hex, records=[])
        for record in journal["records"]:
            if (record["source_id"], record["message_id"]) == (source_id, message_id):
                if _content(record["payload"]) != _content(payload):
                    raise MessageConflictError("该来源消息身份已对应不同内容")
                return WorldReceipt(_record(journal, record), duplicate=True)
        record = _StoredRecord(
            sequence=len(journal["records"]) + 1,
            record_id=uuid4().hex,
            source_id=source_id,
            message_id=message_id,
            payload=deepcopy(payload),
        )
        journal["records"].append(record)
        self._ctx.set(RECORDS, journal)
        return WorldReceipt(_record(journal, record), duplicate=False)

    def get(self, *, source_id: str, message_id: str) -> WorldRecord:
        """按来源消息身份读取；不存在时抛出 KeyError。"""
        _identity(source_id)
        _identity(message_id)
        journal = self._load()
        if journal is not None:
            for record in journal["records"]:
                if (record["source_id"], record["message_id"]) == (source_id, message_id):
                    return _record(journal, record)
        raise KeyError((source_id, message_id))

    def read(
        self, *, after: WorldPosition | None = None, source_id: str | None = None, limit: int = 100
    ) -> tuple[WorldRecord, ...]:
        """按全局序号读取严格晚于 after 的记录，来源过滤不改变序号。

        位置属于别的日志、日志缺失、序号超前或锚定记录不一致时拒绝读取，不静默回退。
        每次最多返回 limit 条；无匹配记录时返回空元组。
        """
        if after is not None and not isinstance(after, WorldPosition):
            raise TypeError("after 必须为 WorldPosition")
        if source_id is not None:
            _identity(source_id)
        if type(limit) is not int or limit <= 0:
            raise ValueError("读取上限必须为正整数")
        journal = self._load()
        if after is not None and (
            journal is None
            or after.journal_id != journal["journal_id"]
            or after.sequence > len(journal["records"])
            or (after.sequence > 0 and journal["records"][after.sequence - 1]["record_id"] != after.record_id)
        ):
            raise CursorError("世界读取位置与当前日志不一致，请核对记录或恢复范围")
        if journal is None:
            return ()
        start = after.sequence if after is not None else 0
        result = []
        for record in journal["records"][start:]:
            if source_id is None or record["source_id"] == source_id:
                result.append(_record(journal, record))
                if len(result) == limit:
                    break
        return tuple(result)
