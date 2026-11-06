"""验证默认装配的输入预算、历史恢复和超限失败不重复执行工具。"""

import asyncio
import json
from typing import cast

import pytest
from aurora_adapter.model.fake import FakeReply
from aurora_agent.input_budget import ModelInputBudget
from aurora_bot.assembly_config import CONFIG, MESSAGES, parse_config
from aurora_core.json_data import encode_json
from test_default_assembly import seed, setup


def configure(ctx, *, streaming=True, enabled=True, budget=2000):
    seed(ctx)
    ctx.set(
        CONFIG,
        {
            **cast(dict, ctx.get(CONFIG)),
            "streaming": streaming,
            "input_budget": {"enabled": enabled, "max_chars": budget},
        },
    )


@pytest.mark.parametrize("streaming", [False, True])
def test_long_history_selected_without_deletion_and_restored_after_restart(tmp_path, streaming):
    async def scenario():
        host, assembly, ctx, _, clients, _, events, _ = setup(tmp_path)
        await host.start(configure=lambda: configure(ctx, streaming=streaming))
        old = [
            {"role": "user", "content": "旧输入" * 2000},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"id": "old", "name": "echo", "arguments": {"text": "旧"}}],
            },
            {"role": "tool", "tool_call_id": "old", "content": "旧结果"},
            {"role": "assistant", "content": "旧回复"},
        ]
        ctx.set(MESSAGES, {"messages": old, "guidance_sequence": 0, "pending": None}, location={"instance_id": "main"})

        def respond(request):
            assert len(encode_json(request)) <= 2000
            assert "旧输入" not in encode_json(request)
            notice = json.loads(request["messages"][0]["content"])
            assert notice["kind"] == "input_budget" and notice["omitted_messages"] >= 4
            latest = request["messages"][-1]
            if latest["role"] == "tool":
                assert latest["tool_call_id"] == "new"
                return FakeReply(("完成当前交流",))
            return FakeReply(tool_calls=({"id": "new", "name": "echo", "arguments": {"text": "当前"}},))

        clients[0].respond = respond
        try:
            assert (await assembly.runtime.submit("当前任务").run.wait()).status == "completed"
            assert events.count("tool.executed") == 1
            history = cast(dict, ctx.get(MESSAGES, location={"instance_id": "main"}))["messages"]
            assert history[:4] == old
            assert not any("input_budget" in m.get("content", "") for m in history)
        finally:
            await host.stop()
        host, assembly, ctx, _, clients, _, events, _ = setup(tmp_path)
        await host.start()
        try:
            assert clients[0].requests == []
            assert cast(dict, ctx.get(MESSAGES, location={"instance_id": "main"}))["messages"] == history
            clients[0].respond = respond
            assert (await assembly.runtime.submit("下一交流").run.wait()).status == "completed"
            assert events.count("tool.executed") == 1
            assert cast(dict, ctx.get(MESSAGES, location={"instance_id": "main"}))["messages"][:4] == old
        finally:
            await host.stop()

    asyncio.run(scenario())


def test_oversized_tool_result_blocks_next_model_call_and_retry_does_not_repeat_tool(tmp_path):
    async def scenario():
        host, assembly, ctx, _, clients, _, events, _ = setup(tmp_path)

        def options():
            configure(ctx)
            config = cast(dict, ctx.get(CONFIG))
            config["tools"][0]["config"]["prefix"] = "完整回执" * 1000
            ctx.set(CONFIG, config)

        await host.start(configure=options)
        clients[0].respond = lambda request: (
            FakeReply(("读取原结果",))
            if request["messages"][-1]["role"] == "tool"
            else FakeReply(tool_calls=({"id": "effect", "name": "echo", "arguments": {"text": "执行"}},))
        )
        try:
            result = await assembly.runtime.submit("原任务").run.wait()
            assert result.status == "failed" and result.error == "ModelInputBudgetExceeded"
            assert len(clients[0].requests) == 1 and events.count("tool.executed") == 1
            history = cast(dict, ctx.get(MESSAGES, location={"instance_id": "main"}))["messages"]
            assert history[-1]["role"] == "tool" and "完整回执" * 1000 in history[-1]["content"]
            assert assembly.defaults is not None
            assembly.defaults.input_budget = ModelInputBudget(12000)
            assert (await assembly.runtime.activate().wait()).status == "completed"
            assert events.count("tool.executed") == 1 and len(clients[0].requests) == 2
            assert sum(m.get("content") == "原任务" for m in clients[0].requests[-1]["messages"]) == 1
        finally:
            await host.stop()

    asyncio.run(scenario())


def test_disabled_preserves_request_and_oversized_guidance_retry_is_not_duplicated(tmp_path):
    async def scenario():
        host, assembly, ctx, _, clients, _, _, _ = setup(tmp_path)
        await host.start(configure=lambda: configure(ctx, enabled=False))
        clients[0].respond = lambda request: FakeReply(("已收到",))
        try:
            assert (await assembly.runtime.submit("历史" * 2000).run.wait()).status == "completed"
            assert len(encode_json(clients[0].requests[0])) > 2000
            assert assembly.defaults is not None
            assembly.defaults.input_budget = ModelInputBudget(2000)
            result = await assembly.runtime.submit("新输入" * 2000).run.wait()
            assert result.status == "failed" and len(clients[0].requests) == 1
            assembly.defaults.input_budget = ModelInputBudget(30000)
            assert (await assembly.runtime.activate().wait()).status == "completed"
            assert len(clients[0].requests) == 2
            assert sum(m.get("content") == "新输入" * 2000 for m in clients[0].requests[-1]["messages"]) == 1
        finally:
            await host.stop()

    asyncio.run(scenario())


@pytest.mark.parametrize("value", [True, 1024.0, 1023, -1, "128000"])
def test_configuration_rejects_invalid_full_budget(value):
    with pytest.raises(ValueError):
        parse_config({"instance_id": "main", "model_role": "reasoning", "input_budget": {"max_chars": value}})


def test_default_configuration_keeps_budget_opt_in():
    assert parse_config({"instance_id": "main", "model_role": "reasoning"})["input_budget"] == {
        "enabled": False,
        "max_chars": 128000,
    }
