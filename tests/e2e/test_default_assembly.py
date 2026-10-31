"""验证恢复配置驱动的默认装配、运行期资源所有权与宿主关闭。"""

import asyncio
import json
from io import StringIO
from typing import cast

import httpx
import pytest
from aurora_bot.assembly import ASSEMBLY, DefaultAssembly
from aurora_bot.assembly import plugin as assembly_plugin
from aurora_bot.assembly_config import AGENTS, CONFIG, RUN, WORK
from aurora_bot.control import ExecutionPlug, ExecutionRequest, component_entries
from aurora_bot.model import plugin as model_plugin
from aurora_bot.operations import RUN_ACTIVATE, RUN_CANCEL, RUN_CONTROL, RUN_SUBMIT
from aurora_bot.react import AgentBusyError
from aurora_bot.react import plugin as react_plugin
from aurora_bot.react_defaults import plugin as defaults_plugin
from aurora_bot.runtime import RunHandle, Submission
from aurora_bot.tools import TOOLS, ToolInstance, ToolSpec
from aurora_bot.tools import plugin as tools_plugin
from aurora_cli.commander import run_cli
from aurora_core.bootstrap import bootstrap
from aurora_core.ctx import Context
from aurora_core.discovery import Plugin, register_plugins
from aurora_core.hooks import HookConnections
from aurora_core.ids import Id
from aurora_core.invocation import invoke_operation
from aurora_core.lifecycle import Lifecycle, install_lifecycle_slots
from aurora_core.persistence import ContextPersistence
from aurora_core.registry import RegistryEntry
from aurora_core.storage import StorageService
from aurora_model_adapter import JsonValue, ModelCapabilities, ToolDefinition, UnsupportedCapability
from aurora_model_adapter.configuration import ADAPTERS, BINDINGS
from aurora_model_adapter.configuration import CONFIG as MODEL_CONFIG
from aurora_model_adapter.fake import FakeModel, FakeReply
from aurora_model_adapter.plugin import plugin as adapter_plugin

ADAPTER = Id("dev.assembly:adapters/fake")
TOOL = Id("dev.assembly:tools/echo")
COMPONENT = Id("dev.assembly:handlers/echo")


@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.parametrize("provider", ["openai", "deepseek"])
def test_litellm_default_assembly_tool_roundtrip_and_restore(tmp_path, monkeypatch, streaming, provider):
    monkeypatch.setenv("LITELLM_LOCAL_MODEL_COST_MAP", "True")
    import openai
    from litellm.llms.custom_httpx.http_handler import AsyncHTTPHandler

    original = openai.AsyncOpenAI.__init__
    transports, requests = [], []

    def handle(request):
        value = json.loads(request.content)
        if provider == "deepseek":
            assert request.url.host == "api.deepseek.com"
            assert value["thinking"] == {"type": "disabled"}
        requests.append(value)
        observed = any(message["role"] == "tool" for message in value["messages"])
        message = {"role": "assistant", "content": "完成" if observed else None}
        if not observed:
            message["tool_calls"] = [
                {"id": "echo-1", "type": "function", "function": {"name": "echo", "arguments": '{"text":"你好"}'}}
            ]
        reason = "stop" if observed else "tool_calls"
        data = {
            "id": "test",
            "object": "chat.completion",
            "created": 1,
            "model": "gpt-4o-mini",
            "choices": [{"index": 0, "message": message, "finish_reason": reason}],
        }
        if not streaming:
            return httpx.Response(200, json=data)
        if not observed:
            message["tool_calls"][0]["index"] = 0
        data["object"] = "chat.completion.chunk"
        data["choices"] = [{"index": 0, "delta": message, "finish_reason": reason}]
        return httpx.Response(
            200,
            content=f"data: {json.dumps(data)}\n\ndata: [DONE]\n\n".encode(),
            headers={"content-type": "text/event-stream"},
        )

    def create_transport(self, **kwargs):
        transport = httpx.AsyncClient(transport=httpx.MockTransport(handle))
        transports.append(transport)
        original(self, http_client=transport, **kwargs)

    monkeypatch.setattr(openai.AsyncOpenAI, "__init__", create_transport)

    def create_http(self, **kwargs):
        transport = httpx.AsyncClient(transport=httpx.MockTransport(handle))
        transports.append(transport)
        return transport

    monkeypatch.setattr(AsyncHTTPHandler, "create_client", create_http)

    async def scenario():
        host, assembly, ctx, _, _, _, _, _ = setup(tmp_path)

        def configure():
            ctx.set(CONFIG, {**settings(), "streaming": streaming})
            ctx.set(
                MODEL_CONFIG,
                {
                    "real": {
                        "adapter": "org.aurora.model_adapter:adapters/litellm",
                        "model": "openai/gpt-4o-mini" if provider == "openai" else "deepseek/deepseek-flash",
                        "credential": "MODEL_TEST_KEY",
                    }
                },
            )
            ctx.set(BINDINGS, {"reasoning": "real"})

        await host.start(configure=configure)
        try:
            assert requests == [] and assembly.agent is not None and assembly.defaults is not None
            execution = ExecutionRequest("sdk-roundtrip")
            assembly.agent.inbox.set(ctx, execution, [{"id": "guide", "sequence": 1, "payload": "回显你好"}])
            await host.run(assembly.activate, execution)
            messages = cast(dict, assembly.defaults.context_state.get(ctx, execution))["messages"]
            observed = next(message for message in messages if message["role"] == "tool")
            assert json.loads(observed["content"])["value"] == "工具:你好"
            assert messages[-1]["content"] == "完成" and len(requests) == 2
            assert cast(dict, assembly.agent.runtime.get(ctx, execution))["status"] == "completed"
        finally:
            await host.stop()
        assert transports[0].is_closed
        assert "runtime-secret" not in (tmp_path / "framework" / "ctx.json").read_text(encoding="utf-8")
        restarted, other, other_ctx, _, _, _, _, _ = setup(tmp_path)
        await restarted.start()
        try:
            assert len(requests) == 2 and other.defaults is not None
            assert cast(dict, other.defaults.context_state.get(other_ctx, execution))["messages"] == messages
        finally:
            await restarted.stop()
        assert len(transports) == 2 and all(transport.is_closed for transport in transports)

    asyncio.run(scenario())


def settings(*, tools=True):
    return {
        "instance_id": "main",
        "model_role": "reasoning",
        "tools": [{"tool": str(TOOL), "instance_id": "echo", "config": {"prefix": "工具:"}}] if tools else [],
    }


def seed(ctx, *, tools=True, credential=False, model="first"):
    ctx.set(CONFIG, settings(tools=tools))
    profile = {"adapter": str(ADAPTER), "model": model}
    if credential:
        profile["credential"] = "MODEL_TEST_KEY"
    ctx.set(MODEL_CONFIG, {"primary": profile, "secondary": {"adapter": str(ADAPTER), "model": "second"}})
    ctx.set(BINDINGS, {"reasoning": "primary"})


def setup(root, *, behavior="normal", capabilities=None, secret="runtime-secret"):
    registry = bootstrap()
    register_plugins(
        registry,
        (adapter_plugin(), model_plugin(), react_plugin(), tools_plugin(), defaults_plugin(), assembly_plugin()),
    )
    install_lifecycle_slots(registry)
    ctx, hooks = Context(registry), HookConnections(registry)
    events, clients, model_calls = [], [], []
    entered = asyncio.Event()
    close_attempts = []

    class Client(FakeModel):
        async def aclose(self):
            close_attempts.append("model")
            if behavior == "close_failure" and len(close_attempts) == 1:
                raise RuntimeError("模型关闭失败")
            await super().aclose()
            events.append("model.closed")

    async def model_factory(config, *, api_key=None):
        model_calls.append((config, api_key))
        events.append("model.created")

        def respond(request):
            if (
                behavior == "quiet"
                or not request.get("tools")
                or any(message["role"] == "tool" for message in request["messages"])
            ):
                return FakeReply((config.model,))
            return FakeReply(tool_calls=({"id": "echo-1", "name": "echo", "arguments": {"text": "你好"}},))

        client = Client(respond, capabilities=capabilities)
        clients.append(client)
        return client

    async def tool_factory(*, ctx, storage, instance_id, input_state, output_state, config):
        events.append("tool.created")

        async def execute(request):
            call = input_state.get(ctx, request)
            assert isinstance(call, dict)
            if behavior == "wait":
                try:
                    entered.set()
                    await asyncio.Event().wait()
                finally:
                    events.append("tool.cancelled")
            output_state.set(ctx, request, config["prefix"] + call["arguments"]["text"])

        async def close():
            events.append("tool.closed")
            storage.set("dev.assembly", "last_close", instance_id)
            ctx.set(AGENTS, "工具最后写入", location={"instance_id": "main", "part": "last_close"})

        return ToolInstance(
            ExecutionPlug(COMPONENT, execute, {"input": input_state, "output": output_state}, instance_id=instance_id),
            close,
        )

    async def placeholder(request):
        raise AssertionError("应调用工厂创建的实例")

    registry.register(RegistryEntry(ADAPTER, "adapter", model_factory, "test", register_to=ADAPTERS))
    registry.register_many(component_entries(COMPONENT, placeholder, placeholder, provider="test"))
    definition: ToolDefinition = {
        "name": "echo",
        "description": "回显",
        "parameters": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
            "additionalProperties": False,
        },
    }
    registry.register(
        RegistryEntry(TOOL, "tool", ToolSpec(COMPONENT, definition, factory=tool_factory), "test", register_to=TOOLS)
    )
    storage = StorageService(root)
    assembly = DefaultAssembly(
        registry=registry, ctx=ctx, hooks=hooks, storage=storage, credential_resolver=lambda _: secret
    )
    host = Lifecycle(
        ctx,
        hooks,
        assembly.components(),
        persistence=ContextPersistence(ctx, storage.snapshot_store()),
        storage=storage,
        timeout=0.05 if behavior == "wait" else 10,
    )
    return host, assembly, ctx, registry, clients, model_calls, events, entered


def test_factory_creation_follows_restore_and_configure_and_start_does_not_activate(tmp_path):
    async def scenario():
        host, assembly, ctx, _, clients, model_calls, events, _ = setup(tmp_path)
        assert events == [] and assembly.agent is None
        await host.start(configure=lambda: seed(ctx, credential=True))
        assert events == ["model.created", "tool.created"] and clients[0].requests == []
        assert model_calls[0][1] == "runtime-secret"
        assert assembly.agent is not None and assembly.defaults is not None
        request = ExecutionRequest("first")
        assembly.agent.inbox.set(ctx, request, [{"id": "event", "sequence": 1, "payload": "开始"}])
        await host.run(assembly.activate, request)
        messages = cast(dict, assembly.defaults.context_state.get(ctx, request))["messages"]
        observed = json.loads(next(message["content"] for message in messages if message["role"] == "tool"))
        assert observed["value"] == "工具:你好"
        await host.stop()
        assert events[-2:] == ["tool.closed", "model.closed"] and clients[0].closed
        snapshot = (tmp_path / "framework" / "ctx.json").read_text(encoding="utf-8")
        assert "runtime-secret" not in snapshot and "工具最后写入" in snapshot

        restored, other, other_ctx, _, new_clients, new_calls, _, _ = setup(tmp_path)
        await restored.start(configure=lambda: other_ctx.set(BINDINGS, {"reasoning": "secondary"}))
        assert new_calls[0][0].model == "second" and new_calls[0][1] is None
        assert new_clients[0] is not clients[0] and new_clients[0].requests == []
        assert other.agent is not None and other.defaults is not None
        assert cast(dict, other.defaults.context_state.get(other_ctx, request))["messages"] == messages
        assert other.agent.progress.get(other_ctx, request) == 1
        assert other.storage.get("dev.assembly", "last_close") == "main/tool/echo"
        assert other.defaults.model.output_state.get(other_ctx, request)
        await restored.stop()
        # 没有新激活的启动/关闭保留最近模型结果。
        saved = json.loads((tmp_path / "framework" / "ctx.json").read_text(encoding="utf-8"))
        assert any(entry["location"].get("part") == "model_output" for entry in saved["entries"])

    asyncio.run(scenario())


def test_shutdown_cancels_inflight_tool_before_closing_resources(tmp_path):
    async def scenario():
        host, assembly, ctx, _, clients, _, events, entered = setup(tmp_path, behavior="wait")
        await host.start(configure=lambda: seed(ctx))
        task = asyncio.create_task(host.run(assembly.activate, ExecutionRequest("cancel")))
        await entered.wait()
        await host.stop()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert events[-3:] == ["tool.cancelled", "tool.closed", "model.closed"]
        assert clients[0].active_streams == 0
        with pytest.raises(RuntimeError, match="关闭"):
            await assembly.activate(ExecutionRequest("late"))
        saved = json.loads((tmp_path / "framework" / "ctx.json").read_text(encoding="utf-8"))
        states = {entry["location"].get("part", entry["id"]): entry["value"] for entry in saved["entries"]}
        assert states[str(RUN)]["status"] == "cancelled"
        assert states["tool_results"]["status"] == "cancelled"

        restarted, restored, restored_ctx, _, restored_clients, _, _, _ = setup(tmp_path, behavior="quiet")
        await restarted.start()
        assert restored_clients[0].requests == []
        await restarted.run(restored.activate, ExecutionRequest("next"))
        assert restored.defaults is not None
        messages = cast(dict, restored.defaults.context_state.get(restored_ctx, ExecutionRequest("next")))["messages"]
        observation = json.loads(next(message["content"] for message in messages if message["role"] == "tool"))
        assert observation["status"] == "cancelled"
        await restarted.stop()

    asyncio.run(scenario())


def test_partial_tool_creation_failure_closes_owned_resources(tmp_path):
    async def scenario():
        host, _, ctx, registry, clients, _, events, _ = setup(tmp_path)

        async def broken_factory(**kwargs):
            events.append("tool.failed")
            raise RuntimeError("工具创建失败")

        other_id = Id("dev.assembly:tools/broken")
        registry.register(
            RegistryEntry(
                other_id,
                "tool",
                ToolSpec(
                    COMPONENT,
                    {
                        "name": "broken",
                        "description": "失败夹具",
                        "parameters": {"type": "object"},
                    },
                    factory=broken_factory,
                ),
                "test",
                register_to=TOOLS,
            )
        )

        def configure():
            seed(ctx)
            value = settings()
            value["tools"].append({"tool": str(other_id), "instance_id": "broken", "config": {}})
            ctx.set(CONFIG, value)

        with pytest.raises(RuntimeError, match="创建失败"):
            await host.start(configure=configure)
        assert events == ["model.created", "tool.created", "tool.failed", "tool.closed", "model.closed"]
        assert clients[0].closed and host.state == "stopped"

    asyncio.run(scenario())


def test_failed_model_close_can_retry_without_reclosing_tools(tmp_path):
    async def scenario():
        host, assembly, ctx, _, clients, _, events, _ = setup(tmp_path, behavior="close_failure")
        await host.start(configure=lambda: seed(ctx))
        with pytest.raises(RuntimeError, match="模型关闭失败"):
            await host.stop()
        assert not clients[0].closed and assembly.client is clients[0]
        assert ctx.get(CONFIG) and host.state == "failed"
        await host.stop()
        assert clients[0].closed and events.count("tool.closed") == 1 and host.state == "stopped"

    asyncio.run(scenario())


def test_capability_rejection_closes_created_model_before_tools(tmp_path):
    async def scenario():
        host, _, ctx, _, clients, _, events, _ = setup(tmp_path, capabilities=ModelCapabilities(streaming=False))
        with pytest.raises(UnsupportedCapability):
            await host.start(configure=lambda: seed(ctx))
        assert events == ["model.created", "model.closed"] and clients[0].closed

    asyncio.run(scenario())


def test_restore_marks_abandoned_run_without_automatic_activation(tmp_path):
    async def scenario():
        host, _, ctx, _, _, _, _, _ = setup(tmp_path)

        def configure():
            seed(ctx, tools=False)

        await host.start(configure=configure)

        # 模拟进程遗留运行；下一次恢复须识别它没有对应任务。
        def leave_abandoned_state():
            ctx.set(
                RUN,
                {"status": "running", "run_id": "abandoned", "execution_id": "old"},
                location={"instance_id": "main"},
            )
            ctx.set(
                WORK,
                {"status": "running", "text": "部分输出"},
                location={"instance_id": "main", "part": "model_output", "run_id": "abandoned"},
            )
            ctx.set(WORK, {"keep": True}, location={"instance_id": "other", "part": "owned"})

        leave_abandoned_state()
        await host.stop()
        restored, _, other_ctx, _, clients, _, _, _ = setup(tmp_path)
        await restored.start()
        state = other_ctx.get(RUN, location={"instance_id": "main"})
        assert isinstance(state, dict)
        assert state["status"] == "failed" and state["error"] == "InterruptedRun"
        assert clients[0].requests == []
        assert other_ctx.get(WORK, location={"instance_id": "other", "part": "owned"}) == {"keep": True}
        await restored.stop()

    asyncio.run(scenario())


def test_registered_assembly_runs_through_cli_host_without_bot_cli_dependency(tmp_path):
    async def scenario():
        host, _, ctx, registry, clients, _, _, _ = setup(tmp_path)
        await host.start(configure=lambda: seed(ctx))
        await host.stop()
        providers = Plugin(
            "testfactories", tuple(entry for entry in registry.entries() if entry.id.namespace == "dev.assembly")
        )
        output = StringIO()
        status = await run_cli(
            ["--data-dir", str(tmp_path), "--assembly", str(ASSEMBLY), "ctx", "get", str(CONFIG)],
            plugins=(
                adapter_plugin(),
                model_plugin(),
                react_plugin(),
                tools_plugin(),
                defaults_plugin(),
                assembly_plugin(),
                providers,
            ),
            output=output,
        )
        assert status == 0 and json.loads(output.getvalue())["instance_id"] == "main"
        assert len(clients) == 2 and all(client.closed and not client.requests for client in clients)

    asyncio.run(scenario())


def gate_model(client, monkeypatch, *, cleanup=None):
    entered, release = asyncio.Event(), asyncio.Event()
    original = client._chunks
    first = True

    async def chunks(request):
        nonlocal first
        if first:
            first = False
            entered.set()
            try:
                await release.wait()
            finally:
                if cleanup is not None:
                    cleanup[0].set()
                    await cleanup[1].wait()
        async for chunk in original(request):
            yield chunk

    monkeypatch.setattr(client, "_chunks", chunks)
    return entered, release


def test_runtime_submission_receipts_sequences_and_repeated_activation(tmp_path):
    async def scenario():
        host, assembly, ctx, _, clients, _, _, _ = setup(tmp_path)
        with pytest.raises(RuntimeError):
            assembly.runtime.submit("尚未启动")
        await host.start(configure=lambda: seed(ctx, tools=False))
        try:
            assert clients[0].requests == [] and assembly.runtime.current is None
            payload: dict[str, JsonValue] = {"text": "第一条"}
            first = assembly.runtime.submit(payload, sequence=3)
            payload["text"] = "外部修改"
            second = assembly.runtime.submit("第二条")
            assert first.sequence == 3 and second.sequence == 4
            assert first.guidance_id != second.guidance_id
            assert first.run is second.run is assembly.runtime.activate()
            before = ctx.snapshot()
            for sequence in (0, 3, 4, True):
                with pytest.raises(ValueError, match="序号"):
                    assembly.runtime.submit("重复", sequence=sequence)
            with pytest.raises(ValueError):
                assembly.runtime.submit(float("nan"))
            assert ctx.snapshot() == before
            result = await first.run.wait()
            assert result.status == "completed" and result.run_id == first.run.run_id
            assert assembly.agent is not None and assembly.defaults is not None
            messages = cast(dict, assembly.defaults.context_state.get(ctx, ExecutionRequest("read")))["messages"]
            assert json.loads(messages[0]["content"]) == {"text": "第一条"}
            assert messages[1]["content"] == "第二条" and len(clients[0].requests) == 1
            assert await assembly.runtime.cancel(first.run.run_id) is False
            third = assembly.runtime.submit("下一次")
            assert third.sequence == 5 and third.run.run_id != first.run.run_id
            assert (await third.run.wait()).status == "completed"
            with pytest.raises(ValueError):
                assembly.runtime.submit("已消费", sequence=5)
        finally:
            await host.stop()
        with pytest.raises(RuntimeError, match="关闭"):
            assembly.runtime.activate()

    asyncio.run(scenario())


def test_runtime_live_guidance_and_cancelled_waiter_keep_current_run(tmp_path, monkeypatch):
    async def scenario():
        host, assembly, ctx, _, clients, _, _, _ = setup(tmp_path)
        await host.start(configure=lambda: seed(ctx, tools=False))
        entered, release = gate_model(clients[0], monkeypatch)
        try:
            first = assembly.runtime.submit("先做这件事")
            await entered.wait()
            waiter = asyncio.create_task(first.run.wait())
            await asyncio.sleep(0)
            waiter.cancel()
            with pytest.raises(asyncio.CancelledError):
                await waiter
            second = assembly.runtime.submit("补充信息")
            assert second.run is first.run and not first.run.done
            release.set()
            assert (await second.run.wait()).status == "completed"
            assert len(clients[0].requests) == 2
            assert clients[0].requests[-1]["messages"][-1]["content"] == "补充信息"
            assert assembly.agent is not None
            assert assembly.agent.progress.get(ctx, ExecutionRequest("read")) == 2
        finally:
            release.set()
            await host.stop()

    asyncio.run(scenario())


@pytest.mark.parametrize("boundary", ["finish", "completed"])
def test_runtime_submission_at_finish_boundary_gets_followup_run(tmp_path, boundary):
    async def scenario():
        host, assembly, ctx, _, clients, _, _, _ = setup(tmp_path)
        await host.start(configure=lambda: seed(ctx, tools=False))
        followups, terminals = [], []

        def observe(change):
            state = change.value
            if change.address.key != RUN or not isinstance(state, dict):
                return
            if state["status"] in ("completed", "cancelled", "failed"):
                terminals.append((state["run_id"], state["status"]))
            match = state["status"] == "completed" if boundary == "completed" else state["phase"] == "finish"
            if match and not followups:
                followups.append(assembly.runtime.submit("收尾期间的输入"))

        subscription = ctx.subscribe(observe, key=RUN)
        try:
            first = assembly.runtime.submit("首次输入")
            assert (await first.run.wait()).status == "completed"
            assert len(followups) == 1 and followups[0].run.run_id != first.run.run_id
            assert (await followups[0].run.wait()).status == "completed"
            assert terminals == [(first.run.run_id, "completed"), (followups[0].run.run_id, "completed")]
            assert len(clients[0].requests) == 2
        finally:
            ctx.unsubscribe(subscription)
            await host.stop()

    asyncio.run(scenario())


def test_runtime_cancel_waits_for_cleanup_and_repeated_cancel_does_not_interrupt_it(tmp_path, monkeypatch):
    async def scenario():
        host, assembly, ctx, _, clients, _, _, _ = setup(tmp_path)
        await host.start(configure=lambda: seed(ctx, tools=False))
        cleaning, released = asyncio.Event(), asyncio.Event()
        entered, _ = gate_model(clients[0], monkeypatch, cleanup=(cleaning, released))
        try:
            submission = assembly.runtime.submit("阻塞调用")
            await entered.wait()
            extra = assembly.runtime.submit("取消时仍未消费的输入")
            first = asyncio.create_task(assembly.runtime.cancel(submission.run.run_id))
            await cleaning.wait()
            assert not first.done() and not submission.run.done
            with pytest.raises(AgentBusyError, match="取消"):
                assembly.runtime.submit("等待清理")
            second = asyncio.create_task(assembly.runtime.cancel(submission.run.run_id))
            await asyncio.sleep(0)
            first.cancel()
            with pytest.raises(asyncio.CancelledError):
                await first
            assert not second.done()
            released.set()
            assert await second is True
            assert (await submission.run.wait()).status == "cancelled"
            assert clients[0].active_streams == 0
            assert assembly.agent is not None
            assert [item["sequence"] for item in assembly.agent.pending(ExecutionRequest("read"))] == [extra.sequence]
            assert assembly.runtime.current is None
            resumed = assembly.runtime.activate()
            assert resumed.run_id != submission.run.run_id
            assert (await resumed.wait()).status == "completed"
            assert await assembly.runtime.cancel(submission.run.run_id) is False
        finally:
            released.set()
            await host.stop()

    asyncio.run(scenario())


def test_runtime_cancel_before_task_start_preserves_input_for_explicit_activation(tmp_path):
    async def scenario():
        host, assembly, ctx, _, clients, _, _, _ = setup(tmp_path)
        await host.start(configure=lambda: seed(ctx, tools=False))
        try:
            submission = assembly.runtime.submit("等待显式恢复")
            assert await assembly.runtime.cancel(submission.run.run_id) is True
            assert (await submission.run.wait()).status == "cancelled"
            assert clients[0].requests == []
            assert assembly.runtime.current is None
            assert (await assembly.runtime.activate().wait()).status == "completed"
            assert len(clients[0].requests) == 1
        finally:
            await host.stop()

    asyncio.run(scenario())


def test_runtime_failure_retains_new_input_without_automatic_retry(tmp_path, monkeypatch):
    async def scenario():
        host, assembly, ctx, _, clients, _, _, _ = setup(tmp_path)
        await host.start(configure=lambda: seed(ctx, tools=False))
        entered, release = gate_model(clients[0], monkeypatch)

        def fail(request):
            raise ValueError("故障夹具")

        clients[0].respond = fail
        try:
            first = assembly.runtime.submit("失败输入")
            await entered.wait()
            second = assembly.runtime.submit("稍后处理")
            release.set()
            result = await first.run.wait()
            assert result.status == "failed" and result.error == "ValueError"
            assert first.run is second.run and assembly.runtime.current is None
            assert len(clients[0].requests) == 1
            clients[0].respond = lambda request: FakeReply(("已恢复",))
            assert (await assembly.runtime.activate().wait()).status == "completed"
            assert clients[0].requests[-1]["messages"][-1]["content"] == "稍后处理"
        finally:
            release.set()
            await host.stop()

    asyncio.run(scenario())


def test_runtime_host_shutdown_cancels_tool_then_closes_resources_and_restores_pending(tmp_path):
    async def scenario():
        host, assembly, ctx, _, clients, _, events, entered = setup(tmp_path, behavior="wait")
        await host.start(configure=lambda: seed(ctx))
        first = assembly.runtime.submit("调用工具")
        await entered.wait()
        queued = assembly.runtime.submit("重启后处理")
        await host.stop()
        assert (await first.run.wait()).status == "cancelled"
        assert events[-3:] == ["tool.cancelled", "tool.closed", "model.closed"]
        assert clients[0].closed
        restored, other, other_ctx, _, new_clients, _, _, _ = setup(tmp_path, behavior="quiet")
        await restored.start()
        try:
            assert new_clients[0].requests == [] and other.runtime.current is None
            with pytest.raises(ValueError):
                other.runtime.submit("重放", sequence=queued.sequence)
            assert (await other.runtime.activate().wait()).status == "completed"
            assert other.agent is not None
            assert other.agent.progress.get(other_ctx, ExecutionRequest("read")) == queued.sequence
            messages = new_clients[0].requests[0]["messages"]
            observation = json.loads(next(message["content"] for message in messages if message["role"] == "tool"))
            assert observation["status"] == "cancelled"
        finally:
            await restored.stop()

    asyncio.run(scenario())


def test_runtime_prevents_mixing_manual_and_managed_owners(tmp_path, monkeypatch):
    async def scenario():
        host, assembly, ctx, _, clients, _, _, _ = setup(tmp_path)
        await host.start(configure=lambda: seed(ctx, tools=False))
        entered, release = gate_model(clients[0], monkeypatch)
        try:
            manual = asyncio.create_task(host.run(assembly.activate, ExecutionRequest("manual")))
            await entered.wait()
            with pytest.raises(AgentBusyError, match="混用"):
                assembly.runtime.submit("不能并行")
            release.set()
            await manual
            managed = assembly.runtime.submit("正式入口")
            with pytest.raises(AgentBusyError, match="混用"):
                await assembly.activate(ExecutionRequest("other"))
            assert (await managed.run.wait()).status == "completed"
        finally:
            release.set()
            await host.stop()

    asyncio.run(scenario())


@pytest.mark.parametrize("finish_error", [False, True])
def test_runtime_queued_cancellation_or_preceding_failure_keeps_input(tmp_path, finish_error):
    async def scenario():
        host, assembly, ctx, registry, clients, _, _, _ = setup(tmp_path)
        await host.start(configure=lambda: seed(ctx, tools=False))
        entered, release = asyncio.Event(), asyncio.Event()
        first_finish = True

        async def finish(request):
            nonlocal first_finish
            if first_finish:
                first_finish = False
                entered.set()
                await release.wait()
                if finish_error:
                    raise ValueError("收尾失败")

        identity = Id("dev.assembly:handlers/finish_gate")
        registry.register_many(component_entries(identity, finish, finish, provider="test"))
        assert assembly.agent is not None
        assembly.agent.slots["finish"].connect(ExecutionPlug(identity, finish))
        try:
            first = assembly.runtime.submit("第一条")
            await entered.wait()
            followup = assembly.runtime.submit("收尾后的输入")
            assert followup.run.run_id != first.run.run_id
            if not finish_error:
                assert await assembly.runtime.cancel(followup.run.run_id) is True
                assert not first.run.done
            release.set()
            result = await first.run.wait()
            next_result = await followup.run.wait()
            if finish_error:
                assert result.status == "failed" and next_result.error == "PreviousRunFailed"
            else:
                assert result.status == "completed" and next_result.status == "cancelled"
            assert len(clients[0].requests) == 1 and assembly.runtime.current is None
            assert assembly.agent.pending(ExecutionRequest("read"))[0]["sequence"] == followup.sequence
            assert (await assembly.runtime.activate().wait()).status == "completed"
            assert len(clients[0].requests) == 2
        finally:
            release.set()
            await host.stop()

    asyncio.run(scenario())


def test_runtime_late_cancel_does_not_change_completed_run(tmp_path):
    async def scenario():
        host, assembly, ctx, _, _, _, _, _ = setup(tmp_path)
        await host.start(configure=lambda: seed(ctx, tools=False))
        cancellations = []

        def observe(change):
            if isinstance(change.value, dict) and change.value.get("status") == "completed":
                cancellations.append(asyncio.create_task(assembly.runtime.cancel(change.value["run_id"])))

        subscription = ctx.subscribe(observe, key=RUN)
        try:
            run = assembly.runtime.submit("完成边界").run
            assert (await run.wait()).status == "completed"
            assert len(cancellations) == 1 and await cancellations[0] is False
            assert (await run.wait()).status == "completed"
        finally:
            ctx.unsubscribe(subscription)
            await host.stop()

    asyncio.run(scenario())


def test_runtime_rejects_reentrant_submission_without_losing_outer_input(tmp_path):
    async def scenario():
        host, assembly, ctx, _, clients, _, _, _ = setup(tmp_path)
        await host.start(configure=lambda: seed(ctx, tools=False))
        checked = []

        def observe(change):
            if not checked:
                checked.append(True)
                with pytest.raises(RuntimeError, match="重入"):
                    assembly.runtime.submit("重入")

        subscription = ctx.subscribe(observe, key=AGENTS, location={"instance_id": "main", "part": "inbox"})
        try:
            submitted = assembly.runtime.submit("外层输入")
            assert (await submitted.run.wait()).status == "completed"
            assert checked == [True]
            assert [m["content"] for m in clients[0].requests[0]["messages"] if m["role"] == "user"] == ["外层输入"]
        finally:
            ctx.unsubscribe(subscription)
            await host.stop()

    asyncio.run(scenario())


def test_runtime_cancelled_close_waiter_keeps_resource_cleanup_alive(tmp_path, monkeypatch):
    async def scenario():
        host, assembly, ctx, _, clients, _, events, _ = setup(tmp_path)
        await host.start(configure=lambda: seed(ctx, tools=False))
        cleaning, release = asyncio.Event(), asyncio.Event()
        entered, _ = gate_model(clients[0], monkeypatch, cleanup=(cleaning, release))
        run = assembly.runtime.submit("等待取消").run
        await entered.wait()
        closing = asyncio.create_task(assembly.runtime.close())
        await cleaning.wait()
        closing.cancel()
        with pytest.raises(asyncio.CancelledError):
            await closing
        assert not run.done and not clients[0].closed
        release.set()
        await assembly.runtime.close()
        assert (await run.wait()).status == "cancelled"
        await host.stop()
        assert events[-1] == "model.closed" and clients[0].closed

    asyncio.run(scenario())


def test_public_run_operations_bind_to_started_bot_and_unbind_on_stop(tmp_path, monkeypatch):
    async def scenario():
        host, assembly, ctx, registry, clients, _, _, _ = setup(tmp_path)
        for identity in (RUN_SUBMIT, RUN_ACTIVATE, RUN_CANCEL):
            entry = registry.get(identity)
            assert entry.kind == "operation" and callable(entry.target)
            assert entry.register_to == Id("org.aurora.core:registries/operations")
        with pytest.raises(LookupError, match="未绑定"):
            await invoke_operation(registry, RUN_SUBMIT, "尚未启动", instance_id="main")
        assert clients == []
        await host.start(configure=lambda: seed(ctx, tools=False))
        entered, release = gate_model(clients[0], monkeypatch)
        try:
            with pytest.raises(TypeError):
                await invoke_operation(registry, RUN_ACTIVATE)
            with pytest.raises(LookupError, match="未绑定"):
                await invoke_operation(registry, RUN_ACTIVATE, instance_id="missing")
            receipt = await invoke_operation(registry, RUN_SUBMIT, "公共入口", instance_id="main", sequence=1)
            assert isinstance(receipt, Submission)
            assert receipt.run is await invoke_operation(registry, RUN_ACTIVATE, instance_id="main")
            with pytest.raises(ValueError, match="序号"):
                await invoke_operation(registry, RUN_SUBMIT, "重复", instance_id="main", sequence=1)
            await entered.wait()
            assert await invoke_operation(registry, RUN_CANCEL, "unknown", instance_id="main") is False
            assert not receipt.run.done
            assert await invoke_operation(registry, RUN_CANCEL, receipt.run.run_id, instance_id="main") is True
            assert (await receipt.run.wait()).status == "cancelled"
            release.set()
            run = await invoke_operation(registry, RUN_ACTIVATE, instance_id="main")
            assert isinstance(run, RunHandle) and (await run.wait()).status == "completed"
            assembly.stop_accepting()
            with pytest.raises(RuntimeError, match="关闭"):
                await invoke_operation(registry, RUN_SUBMIT, "关闭后拒绝", instance_id="main")
        finally:
            release.set()
            await host.stop()
        with pytest.raises(LookupError, match="未绑定"):
            await invoke_operation(registry, RUN_CANCEL, "unknown", instance_id="main")

    asyncio.run(scenario())


@pytest.mark.parametrize("other_identity", ["main", "other"])
def test_public_run_operations_route_instances_without_overwriting_owner(tmp_path, monkeypatch, other_identity):
    async def scenario():
        first, a, ctx_a, registry, clients_a, _, _, _ = setup(tmp_path / "a")
        second, b, ctx_b, other_registry, clients_b, _, _, _ = setup(tmp_path / "b")
        # 显式共享分发服务，验证多个装配的选择和重复身份的启动清理。
        for identity in (RUN_CONTROL, RUN_SUBMIT, RUN_ACTIVATE, RUN_CANCEL):
            other_registry.replace(registry.get(identity))

        def configure_b():
            seed(ctx_b, tools=False)
            config = cast(dict, ctx_b.get(CONFIG))
            ctx_b.set(CONFIG, {**config, "instance_id": other_identity})

        await first.start(configure=lambda: seed(ctx_a, tools=False))
        try:
            if other_identity == "main":
                with pytest.raises(ValueError, match="已经绑定"):
                    await second.start(configure=configure_b)
                assert clients_b[0].closed and not clients_a[0].closed
                run = await invoke_operation(registry, RUN_ACTIVATE, instance_id="main")
                assert isinstance(run, RunHandle) and (await run.wait()).status == "completed"
                return
            await second.start(configure=configure_b)
            entered_a, release_a = gate_model(clients_a[0], monkeypatch)
            entered_b, release_b = gate_model(clients_b[0], monkeypatch)
            try:
                run_a = await invoke_operation(registry, RUN_ACTIVATE, instance_id="main")
                run_b = await invoke_operation(registry, RUN_ACTIVATE, instance_id="other")
                assert isinstance(run_a, RunHandle) and isinstance(run_b, RunHandle)
                assert a.runtime.current is run_a and b.runtime.current is run_b
                await entered_a.wait()
                await entered_b.wait()
                assert await invoke_operation(registry, RUN_CANCEL, run_a.run_id, instance_id="other") is False
                assert not run_a.done and not run_b.done
                assert await invoke_operation(registry, RUN_CANCEL, run_b.run_id, instance_id="other") is True
                assert (await run_b.wait()).status == "cancelled" and not run_a.done
                release_a.set()
                assert (await run_a.wait()).status == "completed"
                await first.stop()
                with pytest.raises(LookupError):
                    await invoke_operation(other_registry, RUN_ACTIVATE, instance_id="main")
                next_run = await invoke_operation(other_registry, RUN_ACTIVATE, instance_id="other")
                assert isinstance(next_run, RunHandle) and (await next_run.wait()).status == "completed"
            finally:
                release_a.set()
                release_b.set()
                await second.stop()
        finally:
            await first.stop()

    asyncio.run(scenario())


def test_run_operations_are_visible_in_cli_without_starting_assembly(tmp_path, monkeypatch):
    monkeypatch.setenv("COLUMNS", "200")
    output = StringIO()
    data = tmp_path / "unused"
    result = asyncio.run(
        run_cli(
            ["--data-dir", str(data), "id", "list"],
            plugins=(
                adapter_plugin(),
                model_plugin(),
                react_plugin(),
                tools_plugin(),
                defaults_plugin(),
                assembly_plugin(),
            ),
            output=output,
        )
    )
    assert result == 0
    for identity in (RUN_SUBMIT, RUN_ACTIVATE, RUN_CANCEL):
        assert str(identity) in output.getvalue()
    assert not data.exists()
