"""验证 MCP 工具发现、agent 执行契约和单次请求边界；不连接外部服务。"""

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import cast

import httpx2
import pytest
from aurora_adapters.mcp import CONFIG_STATE, PROTOCOL_VERSION, MCPClientError, MCPClients
from aurora_adapters.mcp import clients as client_module
from aurora_adapters.mcp.configuration import MCP_CONFIG
from aurora_adapters.mcp.tools import MCPTools
from aurora_agent.tools import TOOLS, ToolExecutor, ToolRejected, ToolSpec
from aurora_control import ExecutionPlug, ExecutionRequest, StateBinding, component_entries
from aurora_core import Id
from aurora_core.bootstrap import bootstrap
from aurora_core.ctx import Context, StateKey
from aurora_core.discovery import load_plugins, register_plugins
from aurora_core.hooks import HookConnections
from aurora_core.lifecycle import install_lifecycle_slots
from aurora_core.registry import RegistryEntry
from aurora_core.storage import StorageService
from mcp.shared.exceptions import MCPError
from mcp.types import (
    CONNECTION_CLOSED,
    HEADER_MISMATCH,
    REQUEST_TIMEOUT,
    CallToolResult,
    InputRequiredResult,
    ListToolsResult,
    ServerCapabilities,
    Tool,
    ToolsCapability,
)

STATE = Id("dev.mcp:state/work")
TOOL = Id("org.aurora.adapters:tools/mcp/local_echo")
PARAMETERS = {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}


def declaration(**changes):
    return {"connection_id": "local", "remote_name": "remote.echo", "name": "local_echo", **changes}


class Session:
    def __init__(self):
        self.calls, self.cursors = [], []
        self.pages = {None: ListToolsResult(tools=[Tool(name="remote.echo", input_schema=PARAMETERS)])}
        self.result = CallToolResult.model_validate(
            {"content": [{"type": "text", "text": "返回"}], "structuredContent": {"text": "返回"}}
        )
        self.error = None
        self.wait = False
        self.entered, self.finished = asyncio.Event(), asyncio.Event()

    async def list_tools(self, *, params):
        self.cursors.append(params.cursor)
        return self.pages[params.cursor]

    async def call_tool(self, name, arguments, *, allow_input_required):
        assert allow_input_required
        self.calls.append((name, arguments))
        self.entered.set()
        try:
            if self.wait:
                await asyncio.Event().wait()
            if self.error is not None:
                raise self.error
            return self.result
        finally:
            self.finished.set()


@pytest.fixture
def environment(tmp_path, monkeypatch):
    session, closed = Session(), []
    client = SimpleNamespace(
        session=session,
        protocol_version=PROTOCOL_VERSION,
        server_capabilities=ServerCapabilities(tools=ToolsCapability()),
    )

    @asynccontextmanager
    async def open_client(config, resolver):
        try:
            yield client
        finally:
            closed.append(config["connection_id"])

    monkeypatch.setattr(client_module, "_open_client", open_client)
    registry = bootstrap()
    install_lifecycle_slots(registry)
    register_plugins(
        registry,
        load_plugins(
            enabled=[
                "aurora_config",
                "aurora_adapters.mcp",
                "aurora_agent.tools",
                "aurora_adapters.mcp.tools",
            ]
        ),
    )
    registry.register(RegistryEntry(STATE, "state_key", StateKey(), "test"))
    ctx, hooks, storage = Context(registry), HookConnections(registry), StorageService(tmp_path)
    config = {"connections": [{"connection_id": "local", "url": "http://localhost/mcp"}], "tools": [declaration()]}
    ctx.set(CONFIG_STATE, config)
    clients = MCPClients(ctx, hooks)
    bridge = MCPTools(registry, ctx, hooks, clients)

    @asynccontextmanager
    async def start(*, discover=True, timeout=1.0):
        clients.configure()
        await clients.prepare()
        try:
            if not discover:
                yield None
                return
            await bridge.prepare()

            def state(name):
                return StateBinding(STATE, (("part", name),))

            executor = ToolExecutor(
                ctx,
                registry,
                hooks,
                request_state=state("request"),
                output_state=state("result"),
                current_state=state("current"),
                timeout=timeout,
            )
            spec = cast(ToolSpec, registry.get(TOOL).target)
            assert spec.factory is not None
            instance = await spec.factory(
                ctx=ctx,
                storage=storage,
                instance_id="echo-instance",
                input_state=state("input"),
                output_state=state("output"),
                config={},
            )
            executor.connect(TOOL, instance.plug)
            yield executor, instance
            if instance.aclose:
                await instance.aclose()
        finally:
            await clients.clean()

    yield SimpleNamespace(**locals())
    hooks.close()
    ctx.close()
    storage.close()


async def submit(env, executor, arguments=None):
    request = ExecutionRequest("run")
    executor.request_state.set(
        env.ctx,
        request,
        {
            "turn_id": "turn",
            "calls": [
                {"id": "call", "name": "local_echo", "arguments": {"text": "输入"} if arguments is None else arguments},
            ],
        },
    )
    await executor.execute(request)
    return cast(dict, executor.output_state.get(env.ctx, request))["results"][0]


@pytest.mark.parametrize(
    "value",
    [
        [declaration(name="bad-name")],
        [declaration(name="a__b")],
        [declaration(name="a" * 65)],
        [declaration(connection_id="missing")],
        [declaration(remote_name="")],
        [declaration(), declaration()],
    ],
)
def test_invalid_selection_rejected_before_network(value):
    with pytest.raises(ValueError):
        MCP_CONFIG.parse({"connections": [{"connection_id": "local", "url": "http://localhost/mcp"}], "tools": value})


def test_discovery_is_explicit_paginated_and_names_stay_stable(environment):
    env = environment
    env.session.pages[None] = ListToolsResult(
        tools=[Tool(name="unused", input_schema={"type": "object"})], next_cursor="p2"
    )
    env.session.pages["p2"] = ListToolsResult(tools=[Tool(name="remote.echo", input_schema=PARAMETERS)])
    assert env.registry.view(register_to=TOOLS) == ()

    async def scenario():
        async with env.start() as (executor, instance):
            assert env.session.cursors == [None, "p2"]
            assert executor.definitions()[0]["name"] == "local_echo"
            assert instance.plug.instance_id == "echo-instance"
            result = await submit(env, executor)
            assert result["status"] == "completed" and result["call_id"] == "call"
            assert result["value"]["structuredContent"] == {"text": "返回"}
            assert env.session.calls == [("remote.echo", {"text": "输入"})]
            with pytest.raises(RuntimeError, match="重建宿主"):
                await env.bridge.prepare()
            assert len(env.registry.view(register_to=TOOLS)) == 1

    asyncio.run(scenario())


@pytest.mark.parametrize("problem", ["missing", "duplicate", "cursor", "schema", "conflict", "capability"])
def test_discovery_failure_does_not_partially_register(environment, problem):
    env = environment
    env.config["tools"].append(declaration(name="second", remote_name="second"))
    tools = [Tool(name="remote.echo", input_schema=PARAMETERS), Tool(name="second", input_schema=PARAMETERS)]
    if problem == "missing":
        tools.pop()
    elif problem == "duplicate":
        tools.append(tools[0])
    elif problem == "schema":
        tools[1] = Tool(name="second", input_schema={"type": "string"})
    elif problem == "conflict":
        env.registry.register(RegistryEntry(Id("org.aurora.adapters:tools/mcp/second"), "test", None, "test"))
    elif problem == "capability":
        env.client.server_capabilities = ServerCapabilities()
    env.session.pages[None] = ListToolsResult(tools=tools, next_cursor="repeat" if problem == "cursor" else None)
    env.session.pages["repeat"] = ListToolsResult(tools=[], next_cursor="repeat")
    env.ctx.set(CONFIG_STATE, env.config)

    async def scenario():
        async with env.start(discover=False):
            before = env.registry.entries()
            with pytest.raises((MCPClientError, ValueError)):
                await env.bridge.prepare()
            assert env.registry.entries() == before
            assert not env.bridge.prepared

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "error,code",
    [
        (MCPError(-32602, "secret-server-message"), "mcp_protocol_error"),
        (MCPError(HEADER_MISMATCH, "secret-server-message"), "mcp_protocol_error"),
        (MCPError(CONNECTION_CLOSED, "secret-server-message"), "mcp_result_unknown"),
        (MCPError(REQUEST_TIMEOUT, "secret-server-message"), "mcp_timeout"),
        (httpx2.ReadError("secret-server-message"), "mcp_result_unknown"),
        (httpx2.ReadTimeout("secret-server-message"), "mcp_timeout"),
        (TimeoutError("secret-server-message"), "mcp_timeout"),
        (ValueError("secret-server-message"), "mcp_invalid_result"),
        (RuntimeError("secret-server-message"), "mcp_invalid_result"),
    ],
)
def test_safe_error_observations_never_retry(environment, error, code, caplog):
    env = environment
    env.session.error = error

    async def scenario():
        async with env.start() as (executor, _):
            result = await submit(env, executor)
            assert result["status"] == "failed" and result["error"]["code"] == code
            assert len(env.session.calls) == 1
            assert "secret-server-message" not in repr(env.ctx.snapshot()) + caplog.text

    asyncio.run(scenario())


@pytest.mark.parametrize("business_error", [False, True])
def test_content_blocks_and_structured_result_are_preserved(environment, business_error):
    env = environment
    env.session.result = CallToolResult.model_validate(
        {
            "content": [
                {"type": "text", "text": "说明"},
                {"type": "image", "data": "AA==", "mimeType": "image/png"},
                {"type": "resource_link", "uri": "test://data", "name": "附件"},
            ],
            "structuredContent": {"nested": [1, False, None]},
            "isError": business_error,
        }
    )

    async def scenario():
        async with env.start() as (executor, _):
            result = await submit(env, executor)
            assert result["status"] == ("failed" if business_error else "completed")
            assert result["value"] == env.session.result.model_dump(mode="json", by_alias=True, exclude_unset=True)
            if business_error:
                assert result["error"]["code"] == "mcp_tool_error"

    asyncio.run(scenario())


def test_input_required_is_observed_without_followup(environment):
    env = environment
    env.session.result = InputRequiredResult(request_state="opaque-secret")

    async def scenario():
        async with env.start() as (executor, _):
            result = await submit(env, executor)
            assert result["error"]["code"] == "mcp_input_required"
            assert "opaque-secret" not in repr(result)
            assert len(env.session.calls) == 1

    asyncio.run(scenario())


@pytest.mark.parametrize("mode", ["arguments", "reject", "closed", "stopped"])
def test_rejected_calls_do_not_reach_server_and_after_hook_observes_failure(environment, mode):
    env = environment

    async def scenario():
        async with env.start() as (executor, instance):
            observed = []

            async def before(request):
                if mode == "reject":
                    raise ToolRejected("拒绝本次执行")

            async def after(request):
                observed.append(executor.current_state.get(env.ctx, request))

            for slot, handler, name in [(executor.before, before, "before"), (executor.after, after, "after")]:
                identity = Id(f"dev.mcp:handlers/{name}")
                env.registry.register_many(component_entries(identity, handler, handler, provider="test"))
                slot.connect(ExecutionPlug(identity, handler))
            if mode == "closed":
                await instance.aclose()
            if mode == "stopped":
                env.clients.stop_accepting()
            result = await submit(env, executor, {"text": 42} if mode == "arguments" else None)
            assert result["status"] == "failed" and env.session.calls == []
            assert observed[0]["result"] == result
            assert env.closed == []

    asyncio.run(scenario())


@pytest.mark.parametrize("mode", ["timeout", "cancel"])
def test_timeout_and_cancellation_finish_borrowed_call_without_replay(environment, mode):
    env = environment
    env.session.wait = True

    async def scenario():
        async with env.start(timeout=0.02 if mode == "timeout" else 10) as (executor, _):
            task = asyncio.create_task(submit(env, executor))
            await env.session.entered.wait()
            if mode == "timeout":
                assert (await task)["error"]["code"] == "timeout"
            else:
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
                result = cast(dict, executor.output_state.get(env.ctx, ExecutionRequest("run")))
                assert result["status"] == "cancelled"
                assert result["results"][0]["error"]["code"] == "cancelled"
            assert env.session.finished.is_set() and len(env.session.calls) == 1
            assert env.closed == []
        assert env.closed == ["local"]
        assert not [task for task in asyncio.all_tasks() if task.get_name().startswith("aurora-mcp:")]

    asyncio.run(scenario())
