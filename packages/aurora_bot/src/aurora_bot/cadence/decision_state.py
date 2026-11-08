"""决策观察和引导回执分别持久化；任何字段都不表示业务已经完成。"""

import math

from .state import _identity, position

CHOICES = ("observe", "attend_events", "review_work")


def initial_state(source_ids: list[str]) -> dict:
    return {
        "version": 2,
        "source_ids": sorted(source_ids),
        "position": None,
        "observation": None,
        "event_position": None,
        "last_guided_at": None,
        "pending": None,
        "receipts": [],
        "error": None,
    }


def _time(value: object) -> None:
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError("cadence 时间必须为非负有限数")


def _decision(value: object) -> None:
    if not isinstance(value, dict) or set(value) != {"id", "at", "choice", "disposition"}:
        raise ValueError("cadence 决策记录无效")
    _identity(value["id"])
    _time(value["at"])
    if value["choice"] not in CHOICES or value["disposition"] not in (
        "observed",
        "cooldown",
        "no_material",
        "busy",
        "pending",
        "submitted",
    ):
        raise ValueError("cadence 决策结果无效")


def validate_decision_state(value: dict) -> None:
    if set(value) != set(initial_state([])):
        raise ValueError("cadence 决策状态字段无效")
    sources = value["source_ids"]
    if not isinstance(sources, list):
        raise TypeError("cadence 来源必须为列表")
    for source in sources:
        _identity(source)
    if len(sources) != len(set(sources)):
        raise ValueError("cadence 来源不能重复")
    observed = position(value["position"])
    guided = position(value["event_position"])
    if guided is not None and (
        observed is None
        or guided.journal_id != observed.journal_id
        or guided.sequence > observed.sequence
        or (guided.sequence == observed.sequence and guided != observed)
    ):
        raise ValueError("cadence 引导位置不得超过观察位置")
    if value["observation"] is not None:
        _decision(value["observation"])
    if value["last_guided_at"] is not None:
        _time(value["last_guided_at"])
    if value["error"] not in (None, "SelectionChanged", "TransferUncertain", "CursorInvalid", "DecisionFailed"):
        raise ValueError("cadence 暂停原因无效")
    pending = value["pending"]
    if pending is not None:
        if not isinstance(pending, dict) or set(pending) != {"decision", "guidance", "position"}:
            raise ValueError("cadence 待投递记录无效")
        _decision(pending["decision"])
        if pending["decision"] != value["observation"] or pending["decision"]["disposition"] != "pending":
            raise ValueError("cadence 待投递记录与观察不一致")
        if pending["decision"]["choice"] == "observe" or not isinstance(pending["guidance"], dict):
            raise ValueError("cadence 待投递引导无效")
        target = position(pending["position"])
        if target is not None and (
            observed is None
            or target.journal_id != observed.journal_id
            or target.sequence > observed.sequence
            or (target.sequence == observed.sequence and target != observed)
        ):
            raise ValueError("cadence 待投递位置超出观察范围")
        if pending["guidance"].get("decision_id") != pending["decision"]["id"]:
            raise ValueError("cadence 待投递引导身份不一致")
    receipts = value["receipts"]
    if not isinstance(receipts, list) or len(receipts) > 64:
        raise ValueError("cadence 只保留最近 64 条投递回执")
    previous = 0
    ids = set()
    for receipt in receipts:
        if not isinstance(receipt, dict) or set(receipt) != {
            "decision",
            "guidance_id",
            "sequence",
            "run_id",
            "references",
        }:
            raise ValueError("cadence 投递回执无效")
        _decision(receipt["decision"])
        if receipt["decision"]["choice"] == "observe" or receipt["decision"]["disposition"] != "submitted":
            raise ValueError("cadence 回执必须关联已投递的决策")
        for key in ("guidance_id", "run_id"):
            _identity(receipt[key])
        references = receipt["references"]
        if not isinstance(references, list) or not references:
            raise ValueError("cadence 回执必须保留所引导材料的引用")
        for reference in references:
            if not isinstance(reference, dict):
                raise TypeError("cadence 材料引用必须为对象")
            if receipt["decision"]["choice"] == "attend_events":
                if set(reference) != {"kind", "journal_id", "record_id"} or reference["kind"] != "world_event":
                    raise ValueError("cadence 事件引用无效")
                _identity(reference["journal_id"])
                _identity(reference["record_id"])
            else:
                if set(reference) != {"kind", "note_id", "revision"} or reference["kind"] != "work_note":
                    raise ValueError("cadence 笔记引用无效")
                _identity(reference["note_id"])
                if type(reference["revision"]) is not int or reference["revision"] < 1:
                    raise ValueError("cadence 笔记版本无效")
        if type(receipt["sequence"]) is not int or receipt["sequence"] <= previous:
            raise ValueError("cadence 引导序号必须递增")
        if receipt["guidance_id"] in ids or receipt["decision"]["id"] in ids:
            raise ValueError("cadence 引导或决策身份重复")
        ids.update((receipt["guidance_id"], receipt["decision"]["id"]))
        previous = receipt["sequence"]
    if receipts and value["last_guided_at"] != receipts[-1]["decision"]["at"]:
        raise ValueError("cadence 最后投递时间与回执不一致")
