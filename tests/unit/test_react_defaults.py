"""验证正式默认阶段的工具往返、失败观察、引导去重与中断接纳。"""

import asyncio
import json
from typing import cast

import pytest
from aurora_bot.model import ModelCall
from aurora_bot.model import plugin as model_plugin
from aurora_bot.react import ReActAgent
from aurora_bot.react import plugin as react_plugin
from aurora_bot.react_defaults import ReActContext, ReActDefaults
from aurora_bot.react_defaults import plugin as defaults_plugin
from aurora_bot.tools import TOOLS, ToolExecutor, ToolSpec
from aurora_bot.tools import plugin as tools_plugin
from aurora_control import ExecutionPlug, ExecutionRequest, InstanceStateBinding, StateBinding, component_entries
from aurora_core.bootstrap import bootstrap
from aurora_core.ctx import Context, StateKey
from aurora_core.discovery import register_plugins
from aurora_core.hooks import HookConnections
from aurora_core.ids import Id
from aurora_core.registry import RegistryEntry
from aurora_model_adapter import JsonValue, ModelProtocolError, ToolCall
from aurora_model_adapter.fake import FakeModel, FakeReply

STATE = Id("dev.defaults:state/data")
COMPONENT = Id("dev.defaults:handlers/compute")


@pytest.fixture
def factory():
    resources = []

    def create(respond, *, behavior="success"):
        registry = bootstrap()
        register_plugins(registry, (react_plugin(), model_plugin(), tools_plugin(), defaults_plugin()))
        registry.register(RegistryEntry(STATE, "state_key", StateKey(), "test"))
        ctx, hooks = Context(registry), HookConnections(registry)
        client = FakeModel(respond)
        resources.append((ctx, hooks, client))

        def fixed(name):
            return InstanceStateBinding(STATE, (("name", name),))

        def transient(name):
            return StateBinding(STATE, (("name", name),))

        agent = ReActAgent(
            ctx,
            hooks,
            inbox=fixed("inbox"),
            progress=fixed("progress"),
            runtime=fixed("runtime"),
            batch=transient("batch"),
            decision=transient("decision"),
            max_iterations=5,
        )
        model = ModelCall(ctx, client, request_state=transient("request"), output_state=transient("response"))
        tools = ToolExecutor(
            ctx,
            registry,
            hooks,
            request_state=transient("calls"),
            output_state=transient("results"),
            current_state=transient("current"),
            timeout=10,
        )
        tool_input, tool_output = transient("input"), transient("output")
        calls, cleaned = [], []
        entered = asyncio.Event()

        async def compute(request):
            call = tool_input.get(ctx, request)
            assert isinstance(call, dict)
            calls.append(call)
            if behavior == "fail":
                raise ValueError("执行失败")
            if behavior == "wait" and call["id"] == "two":
                try:
                    entered.set()
                    await asyncio.Event().wait()
                finally:
                    cleaned.append(call["id"])
            tool_output.set(ctx, request, call["arguments"]["n"] * 2)

        registry.register_many(component_entries(COMPONENT, compute, compute, provider="test"))
        identity = Id("dev.defaults:tools/compute")
        registry.register(
            RegistryEntry(
                identity,
                "tool",
                ToolSpec(
                    COMPONENT,
                    {
                        "name": "compute",
                        "description": "数值翻倍",
                        "parameters": {
                            "type": "object",
                            "properties": {"n": {"type": "integer"}},
                            "required": ["n"],
                            "additionalProperties": False,
                        },
                    },
                ),
                "test",
                register_to=TOOLS,
            )
        )
        tools.connect(identity, ExecutionPlug(COMPONENT, compute, {"input": tool_input, "output": tool_output}))
        defaults = ReActDefaults(
            agent, model, tools, context_state=fixed("context"), system_prompt="自主判断是否需要行动"
        )
        defaults.connect()
        return ctx, agent, defaults, client, calls, entered, cleaned

    yield create
    for ctx, hooks, client in resources:
        asyncio.run(client.aclose())
        hooks.close()
        ctx.close()


def tool_call(
    identity: str = "one", *, name: str = "compute", arguments: dict[str, JsonValue] | None = None
) -> ToolCall:
    return {"id": identity, "name": name, "arguments": {"n": 3} if arguments is None else arguments}


@pytest.mark.parametrize("outcome", ["success", "fail", "unknown", "invalid"])
def test_tools_and_failures_return_to_model_as_observations(factory, outcome):
    def respond(request):
        if request["messages"][-1]["role"] == "tool":
            return FakeReply(("已经理解结果",))
        return FakeReply(
            tool_calls=(
                tool_call(
                    name="unknown" if outcome == "unknown" else "compute",
                    arguments={"n": "bad"} if outcome == "invalid" else None,
                ),
            )
        )

    ctx, agent, defaults, client, calls, _, _ = factory(respond, behavior="fail" if outcome == "fail" else "success")
    request = ExecutionRequest("run")
    asyncio.run(agent.execute(request))
    assert len(client.requests) == 2
    observation = json.loads(client.requests[-1]["messages"][-1]["content"])
    assert observation["status"] == ("completed" if outcome == "success" else "failed")
    assert len(calls) == (0 if outcome in ("unknown", "invalid") else 1)
    assert cast(dict, agent.runtime.get(ctx, request))["status"] == "completed"
    context = cast(ReActContext, defaults.context_state.get(ctx, request))
    assert context["pending"] is None and context["messages"][-1]["content"] == "已经理解结果"


def test_guidance_during_stream_is_seen_without_discarding_tools(factory):
    replies = []

    def respond(request):
        replies.append(request)
        return FakeReply(("准备",), tool_calls=(tool_call(),)) if len(replies) == 1 else FakeReply()

    ctx, agent, defaults, client, calls, _, _ = factory(respond)
    request = ExecutionRequest("run")
    initial = {"id": "first", "sequence": 1, "payload": "执行计算"}
    steer = {"id": "second", "sequence": 2, "payload": {"event": "保留计算结果"}}
    agent.inbox.set(ctx, request, [initial])
    injected = []

    def observe(change):
        if not injected and change.action == "set" and change.value.get("text") == "准备":
            injected.append(True)
            agent.inbox.set(ctx, request, [initial, steer])

    ctx.subscribe(observe, key=STATE, location=dict(defaults.model.output_state.address(request).location))
    asyncio.run(agent.execute(request))
    context = cast(ReActContext, defaults.context_state.get(ctx, request))
    assert context["guidance_sequence"] == agent.progress.get(ctx, request) == 2
    assert len(calls) == 1 and len(client.requests) == 2
    assert [row["role"] for row in context["messages"]] == ["user", "assistant", "tool", "user"]
    assert json.loads(context["messages"][-1]["content"]) == steer["payload"]
    asyncio.run(agent.execute(ExecutionRequest("again")))
    assert len(calls) == 1
    assert cast(ReActContext, defaults.context_state.get(ctx, request)) == context


def test_prepare_is_idempotent_when_context_was_saved_before_progress(factory):
    ctx, agent, defaults, _, _, _, _ = factory(lambda _: FakeReply())
    request = ExecutionRequest("run")
    incoming = [{"id": "first", "sequence": 1, "payload": "保持安静"}]
    agent.inbox.set(ctx, request, incoming)
    agent.batch.set(ctx, request, incoming)
    asyncio.run(defaults.build_prompt(request))
    asyncio.run(agent.execute(request))
    context = cast(ReActContext, defaults.context_state.get(ctx, request))
    assert context["messages"] == [{"role": "user", "content": "保持安静"}]
    assert agent.progress.get(ctx, request) == 1


def test_cancelled_batch_is_observed_next_time_without_reexecution(factory):
    responses = []

    def respond(request):
        responses.append(request)
        return (
            FakeReply(tool_calls=(tool_call("one"), tool_call("two"), tool_call("three")))
            if len(responses) == 1
            else FakeReply()
        )

    ctx, agent, defaults, client, calls, entered, cleaned = factory(respond, behavior="wait")
    request = ExecutionRequest("first")

    async def scenario():
        task = asyncio.create_task(agent.execute(request))
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert cast(ReActContext, defaults.context_state.get(ctx, request))["pending"] is not None
        await agent.execute(ExecutionRequest("next"))

    asyncio.run(scenario())
    assert [call["id"] for call in calls] == ["one", "two"] and cleaned == ["two"]
    messages = client.requests[-1]["messages"]
    results = [json.loads(row["content"]) for row in messages if row["role"] == "tool"]
    assert results[0]["value"] == 6
    assert [row["error"]["code"] for row in results[1:]] == ["cancelled", "not_executed"]
    assert cast(ReActContext, defaults.context_state.get(ctx, request))["pending"] is None


def test_missing_results_are_not_replaced_by_stale_batch(factory):
    ctx, agent, defaults, client, calls, _, _ = factory(lambda _: FakeReply())
    request = ExecutionRequest("next")
    defaults.context_state.set(
        ctx,
        request,
        {
            "messages": [],
            "guidance_sequence": 0,
            "pending": {
                "run_id": "previous",
                "turn_id": "expected",
                "message": {"role": "assistant", "content": "", "tool_calls": [tool_call()]},
            },
        },
    )
    defaults.tools.output_state.set(
        ctx,
        ExecutionRequest("previous"),
        {
            "turn_id": "stale",
            "status": "completed",
            "results": [{"call_id": "one", "name": "compute", "status": "completed", "value": 999}],
        },
    )
    asyncio.run(agent.execute(request))
    observation = json.loads(client.requests[-1]["messages"][-1]["content"])
    assert observation["error"]["code"] == "interrupted" and calls == []


@pytest.mark.parametrize("finish_reason", ["length", "content_filter"])
def test_incomplete_model_response_cannot_be_treated_as_success(factory, finish_reason):
    ctx, agent, _, _, calls, _, _ = factory(lambda _: FakeReply(("部分输出",), finish_reason=finish_reason))
    request = ExecutionRequest("run")
    with pytest.raises(ModelProtocolError):
        asyncio.run(agent.execute(request))
    assert calls == [] and cast(dict, agent.runtime.get(ctx, request))["status"] == "failed"
