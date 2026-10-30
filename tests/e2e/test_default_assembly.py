"""验证恢复配置驱动的默认装配、运行期资源所有权与宿主关闭。"""

import asyncio
import json
from io import StringIO
from typing import cast

import pytest
from aurora_bot.assembly import ASSEMBLY, DefaultAssembly
from aurora_bot.assembly import plugin as assembly_plugin
from aurora_bot.assembly_config import AGENTS, CONFIG, RUN, WORK
from aurora_bot.control import ExecutionPlug, ExecutionRequest, component_entries
from aurora_bot.model import plugin as model_plugin
from aurora_bot.react import plugin as react_plugin
from aurora_bot.react_defaults import plugin as defaults_plugin
from aurora_bot.tools import TOOLS, ToolInstance, ToolSpec
from aurora_bot.tools import plugin as tools_plugin
from aurora_cli.commander import run_cli
from aurora_core.bootstrap import bootstrap
from aurora_core.ctx import Context
from aurora_core.discovery import Plugin, register_plugins
from aurora_core.hooks import HookConnections
from aurora_core.ids import Id
from aurora_core.lifecycle import Lifecycle, install_lifecycle_slots
from aurora_core.persistence import ContextPersistence
from aurora_core.registry import RegistryEntry
from aurora_core.storage import StorageService
from aurora_model_adapter import ModelCapabilities, ToolDefinition, UnsupportedCapability
from aurora_model_adapter.configuration import ADAPTERS, BINDINGS
from aurora_model_adapter.configuration import CONFIG as MODEL_CONFIG
from aurora_model_adapter.fake import FakeModel, FakeReply
from aurora_model_adapter.plugin import plugin as adapter_plugin

ADAPTER = Id("dev.assembly:adapters/fake")
TOOL = Id("dev.assembly:tools/echo")
COMPONENT = Id("dev.assembly:handlers/echo")


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
