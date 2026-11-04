"""验证 cadence 的显式选择、插件依赖与消费状态校验。"""

from copy import deepcopy

import pytest
from aurora_bot.cadence.state import CADENCE_CONFIG, validate_checkpoint
from aurora_core.discovery import load_plugins


@pytest.mark.parametrize(
    "value",
    [{"extra": True}, {"source_ids": [""]}, {"source_ids": [" "]}, {"source_ids": [1]}, {"source_ids": ["a", "a"]}],
)
def test_invalid_source_selection(value):
    with pytest.raises(ValueError):
        CADENCE_CONFIG.parse(value)


def test_empty_selection_is_inert_and_plugin_dependencies_are_explicit():
    assert CADENCE_CONFIG.parse({}) == {"source_ids": []}
    with pytest.raises(ValueError, match="依赖"):
        load_plugins(enabled=["aurora_bot.cadence"])


def checkpoint():
    return {
        "version": 1,
        "source_ids": ["source"],
        "position": {"journal_id": "journal", "sequence": 2, "record_id": "record"},
        "pending": None,
        "error": None,
        "receipts": [
            {
                "message": {
                    "position": {"journal_id": "journal", "sequence": 2, "record_id": "record"},
                    "source_id": "source",
                    "message_id": "message",
                    "payload": {"text": "原始消息"},
                },
                "guidance_id": "guidance",
                "sequence": 3,
                "run_id": "run",
            }
        ],
    }


@pytest.mark.parametrize(
    "fault", ["version", "journal", "cursor", "source", "duplicate", "pending", "guidance", "error"]
)
def test_corrupt_checkpoint_is_rejected(fault):
    state = checkpoint()
    validate_checkpoint(state)
    if fault == "version":
        state["version"] = True
    elif fault == "journal":
        state["position"]["journal_id"] = "other"
    elif fault == "cursor":
        state["position"]["sequence"] = 1
    elif fault == "source":
        state["source_ids"] = ["other"]
    elif fault == "duplicate":
        state["receipts"] *= 2
    elif fault == "pending":
        state["pending"] = deepcopy(state["receipts"][0]["message"])
    elif fault == "guidance":
        state["receipts"][0]["sequence"] = True
    else:
        state["error"] = "arbitrary error text"
    with pytest.raises((ValueError, TypeError)):
        validate_checkpoint(state)
