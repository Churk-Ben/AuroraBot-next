"""验证完整请求预算、完整交流边界及原历史保留。"""

from copy import deepcopy

import pytest
from aurora_agent.input_budget import ModelInputBudget, ModelInputBudgetExceeded
from aurora_core.json_data import encode_json


def test_exact_budget_includes_system_tools_metadata_and_escaped_unicode():
    request = {"messages": [{"role": "system", "content": '文😀\n"\\' * 500}], "tools": []}
    size = len(encode_json(request))
    assert ModelInputBudget(size).apply(request, history_start=1) == request
    with pytest.raises(ModelInputBudgetExceeded) as failure:
        ModelInputBudget(size - 1).apply(request, history_start=1)
    assert failure.value.required_chars == size
    assert "文" not in str(failure.value)


def test_old_exchange_removed_as_whole_and_tool_relations_stay_intact():
    prefix = [{"role": "system", "content": "规则"}, {"role": "user", "content": "当前观察"}]
    old = [{"role": "user", "content": "旧交流" * 2000}, {"role": "assistant", "content": "已回复"}]
    current = [
        {"role": "user", "content": "当前任务"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "a", "name": "send", "arguments": {}}]},
        {"role": "tool", "tool_call_id": "a", "content": "结果待核实"},
        {"role": "user", "content": "追加引导"},
    ]
    request = {"messages": prefix + old + current, "tools": [{"name": "send", "parameters": {"type": "object"}}]}
    before = deepcopy(request)
    result = ModelInputBudget(1200).apply(request, history_start=2)
    assert request == before and result["tools"] == request["tools"]
    assert result["messages"][:2] == prefix and result["messages"][-4:] == current
    assert len(encode_json(result)) <= 1200
    assert '"omitted_messages":2' in result["messages"][2]["content"].replace(" ", "")


def test_only_enough_old_exchanges_removed_and_latest_completed_one_retained():
    old = [{"role": "user", "content": "旧" * 1000}, {"role": "assistant", "content": "旧回复"}]
    recent = [{"role": "user", "content": "最近"}, {"role": "assistant", "content": "最近回复"}]
    request = {"messages": old + recent}
    result = ModelInputBudget(1024).apply(request, history_start=0)
    assert result["messages"][-2:] == recent
    with pytest.raises(ModelInputBudgetExceeded):
        ModelInputBudget(1024).apply({"messages": old}, history_start=0)
    exchanges = [
        message
        for number in range(3)
        for message in (
            {"role": "user", "content": str(number) * 700},
            {"role": "assistant", "content": f"回复 {number}"},
        )
    ]
    result = ModelInputBudget(2000).apply({"messages": exchanges + recent}, history_start=0)
    assert result["messages"][1:] == exchanges[2:] + recent


@pytest.mark.parametrize("part", ["system", "view", "tools", "current", "result"])
def test_required_material_is_never_silently_truncated(part):
    prefix = [{"role": "system", "content": "规则"}, {"role": "user", "content": "观察"}]
    current = [{"role": "user", "content": "当前任务"}]
    tools = [{"name": "tool", "description": "描述", "parameters": {"type": "object"}}]
    if part in ("system", "view"):
        prefix[0 if part == "system" else 1]["content"] = "固定内容" * 1000
    elif part == "tools":
        tools[0]["description"] = "工具定义" * 1000
    elif part == "current":
        current[0]["content"] = "当前输入" * 1000
    else:
        current += [
            {"role": "assistant", "content": "", "tool_calls": [{"id": "call", "name": "tool", "arguments": {}}]},
            {"role": "tool", "tool_call_id": "call", "content": "完整结果" * 1000},
        ]
    request = {"messages": prefix + [{"role": "assistant", "content": "旧回复"}] + current, "tools": tools}
    before = deepcopy(request)
    with pytest.raises(ModelInputBudgetExceeded):
        ModelInputBudget(1024).apply(request, history_start=2)
    assert request == before


@pytest.mark.parametrize("budget", [True, 1024.0, 0, -1, 1023])
def test_invalid_budgets_rejected(budget):
    with pytest.raises(ValueError):
        ModelInputBudget(budget)
