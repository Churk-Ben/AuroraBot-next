"""单宿主内的世界记录、来源去重和持久读取位置。"""

import json
from collections.abc import Callable, Mapping
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


@dataclass(frozen=True)
class RecordRetention:
    """单个来源的保留上限；expired 判断载荷副本，未声明的来源保留全部记录。"""

    limit: int
    expired: Callable[[object], bool] | None = None

    def __post_init__(self) -> None:
        if type(self.limit) is not int or self.limit < 1:
            raise ValueError("记录保留数量必须为正整数")
        if self.expired is not None and not callable(self.expired):
            raise TypeError("记录过期判断必须可调用")


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
    next_sequence: int
    pruned_through: int
    pruned_record_id: str | None


def validate_records(value: object) -> None:
    """校验 v1 完整日志或 v2 保留窗口；裁剪不能复用序号或掩盖未声明的缺口。"""
    encode_json(value)
    if not isinstance(value, dict):
        raise TypeError("世界日志结构无效")
    if type(value.get("version")) is not int or value["version"] not in (1, 2):
        raise ValueError("不支持的世界日志版本")
    fields = {"version", "journal_id", "records"}
    if value["version"] == 2:
        fields |= {"next_sequence", "pruned_through", "pruned_record_id"}
    if set(value) != fields:
        raise ValueError("世界日志结构无效")
    _identity(value["journal_id"])
    records = value["records"]
    if not isinstance(records, list):
        raise TypeError("世界记录必须为列表")
    next_sequence = value.get("next_sequence", len(records) + 1)
    pruned = value.get("pruned_through", 0)
    if type(next_sequence) is not int or type(pruned) is not int or not 0 <= pruned < next_sequence:
        raise ValueError("世界日志序号边界无效")
    anchor = value.get("pruned_record_id")
    if pruned:
        _identity(anchor)
    elif anchor is not None:
        raise ValueError("尚未裁剪的日志不能声明裁剪锚点")
    identities: set[tuple[str, str]] = set()
    record_ids: set[str] = set()
    previous = 0
    for record in records:
        if not isinstance(record, dict) or set(record) != {
            "sequence",
            "record_id",
            "source_id",
            "message_id",
            "payload",
        }:
            raise ValueError("世界记录结构无效")
        sequence = record["sequence"]
        if (
            type(sequence) is not int
            or not previous < sequence < next_sequence
            or sequence == pruned
            or (sequence > previous + 1 and sequence - 1 > pruned)
        ):
            raise ValueError("世界记录序号与保留边界不一致")
        previous = sequence
        for field in ("record_id", "source_id", "message_id"):
            _identity(record[field])
        identity = (record["source_id"], record["message_id"])
        if identity in identities or record["record_id"] in record_ids:
            raise ValueError("世界记录身份重复")
        identities.add(identity)
        record_ids.add(record["record_id"])
    if max(previous, pruned) != next_sequence - 1:
        raise ValueError("世界日志末尾序号缺失")
    if anchor in record_ids:
        raise ValueError("已裁剪的记录身份不能仍在保留窗口内")


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

    日志随宿主 ContextPersistence 保存，接纳与落盘之间存在崩溃窗口。默认保留全部，
    显式保留规则只裁剪指定来源；去重只覆盖仍保留的消息，已裁剪消息再次提交视为新输入。
    v1 在内存中读取，下一次写入升级 v2；序号单调递增，裁剪不改变存活记录身份。
    每次操作复制完整日志，适用于首版有限规模输入，不承诺大容量消息存储性能。
    """

    def __init__(self, ctx: Context) -> None:
        self._ctx = ctx

    def _load(self) -> _Journal | None:
        if not self._ctx.list(key=RECORDS, location={}):
            return None
        journal = cast(_Journal, self._ctx.get(RECORDS))
        if journal["version"] == 1:
            journal.update(
                version=2, next_sequence=len(journal["records"]) + 1, pruned_through=0, pruned_record_id=None
            )
        return journal

    @staticmethod
    def _retain(journal: _Journal, retention: Mapping[str, RecordRetention]) -> int:
        removed: set[int] = set()
        for source_id, policy in retention.items():
            _identity(source_id)
            if not isinstance(policy, RecordRetention):
                raise TypeError("来源保留规则必须为 RecordRetention")
            kept = 0
            for record in reversed(journal["records"]):
                if record["source_id"] != source_id:
                    continue
                if kept >= policy.limit or (policy.expired is not None and policy.expired(deepcopy(record["payload"]))):
                    removed.add(record["sequence"])
                else:
                    kept += 1
        if removed:
            latest = max(removed)
            if latest > journal["pruned_through"]:
                journal["pruned_through"] = latest
                journal["pruned_record_id"] = next(
                    record["record_id"] for record in journal["records"] if record["sequence"] == latest
                )
            journal["records"] = [record for record in journal["records"] if record["sequence"] not in removed]
        return len(removed)

    def prune(self, retention: Mapping[str, RecordRetention]) -> int:
        """原子裁剪指定来源；没有删除时不写状态、不升级快照或通知订阅者。"""
        journal = self._load()
        if journal is None:
            return 0
        removed = self._retain(journal, retention)
        if removed:
            self._ctx.set(RECORDS, journal)
        return removed

    def append(
        self,
        *,
        source_id: str,
        message_id: str,
        payload: object,
        retention: Mapping[str, RecordRetention] | None = None,
    ) -> WorldReceipt:
        """保留窗口内按身份去重；追加与裁剪一次提交，仅裁剪也会发布变化。"""
        _identity(source_id)
        _identity(message_id)
        encode_json(payload)
        journal = self._load()
        if journal is None:
            journal = _Journal(
                version=2, journal_id=uuid4().hex, records=[], next_sequence=1, pruned_through=0, pruned_record_id=None
            )
        for record in journal["records"]:
            if (record["source_id"], record["message_id"]) == (source_id, message_id):
                if _content(record["payload"]) != _content(payload):
                    raise MessageConflictError("该来源消息身份已对应不同内容")
                receipt = WorldReceipt(_record(journal, record), duplicate=True)
                if self._retain(journal, retention or {}):
                    self._ctx.set(RECORDS, journal)
                return receipt
        record = _StoredRecord(
            sequence=journal["next_sequence"],
            record_id=uuid4().hex,
            source_id=source_id,
            message_id=message_id,
            payload=deepcopy(payload),
        )
        journal["records"].append(record)
        journal["next_sequence"] += 1
        self._retain(journal, retention or {})
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

        日志缺失、身份不符、序号超前或位置早于裁剪边界时拒绝读取，不静默回退。
        恰好位于裁剪边界的位置凭保留的记录身份继续读取；不提供 after 时读取当前窗口。
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
            or after.sequence >= journal["next_sequence"]
            or after.sequence < journal["pruned_through"]
            or (
                after.sequence > 0
                and not (after.sequence == journal["pruned_through"] and after.record_id == journal["pruned_record_id"])
                and not any(
                    record["sequence"] == after.sequence and record["record_id"] == after.record_id
                    for record in journal["records"]
                )
            )
        ):
            raise CursorError("世界读取位置与当前日志不一致，请核对记录或恢复范围")
        if journal is None:
            return ()
        start = after.sequence if after is not None else 0
        result = []
        for record in journal["records"]:
            if record["sequence"] <= start:
                continue
            if source_id is None or record["source_id"] == source_id:
                result.append(_record(journal, record))
                if len(result) == limit:
                    break
        return tuple(result)
