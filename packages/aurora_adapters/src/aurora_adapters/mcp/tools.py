"""将显式选择的 MCP 工具登记到 agent；客户端资源始终由 MCPClients 持有。"""

import asyncio
from typing import cast

import httpx2
from aurora_agent.tools import TOOLS, ToolExecutionError, ToolInstance, ToolSpec
from aurora_control import ExecutionPlug, ExecutionRequest, StateBinding, component_entries
from aurora_core import Id, entry_from, hook_handler
from aurora_core.ctx import Context
from aurora_core.discovery import Plugin
from aurora_core.hooks import HookConnections
from aurora_core.json_data import encode_json
from aurora_core.lifecycle import PREPARE, LifecycleComponent
from aurora_core.registry import DefinitionRegistry, RegistryEntry
from aurora_core.storage import StorageService
from aurora_model_adapter import JsonValue, ToolCall
from mcp.shared.exceptions import MCPError
from mcp.types import CONNECTION_CLOSED, REQUEST_TIMEOUT, CallToolResult, PaginatedRequestParams, Tool

from .clients import MCPClients
from .configuration import CONFIG_STATE, MCP_CONFIG, configured_servers
from .errors import MCPClientError

COMPONENT = Id("org.aurora.adapters:components/mcp/tool")


class _Tool:
    """单个执行插头；关闭只封闭本实例，已借用请求由调用方和客户端所有者收束。"""

    def __init__(
        self,
        clients: MCPClients,
        connection_id: str,
        remote_name: str,
        timeout: float,
        ctx: Context,
        input_state: StateBinding,
        output_state: StateBinding,
    ) -> None:
        self.clients, self.connection_id, self.remote_name = clients, connection_id, remote_name
        self.timeout = timeout
        self.ctx, self.input_state, self.output_state = ctx, input_state, output_state
        self.closed = False

    async def close(self) -> None:
        self.closed = True

    async def execute(self, request: ExecutionRequest) -> None:
        if self.closed:
            raise ToolExecutionError("mcp_unavailable", "MCP 工具实例已关闭，请求未提交")
        call = cast(ToolCall, self.input_state.get(self.ctx, request))
        value: JsonValue = None
        failure: ToolExecutionError | None = None
        submitted = False
        try:
            async with self.clients.connection(self.connection_id) as client:
                try:
                    submitted = True
                    async with asyncio.timeout(self.timeout):
                        result = await client.session.call_tool(
                            self.remote_name, call["arguments"], allow_input_required=True
                        )
                    if not isinstance(result, CallToolResult):
                        failure = ToolExecutionError(
                            "mcp_input_required", "MCP 工具需要额外交互，未续发请求，动作结果需核实"
                        )
                    else:
                        value = cast(JsonValue, result.model_dump(mode="json", by_alias=True, exclude_unset=True))
                        encode_json(value)
                        if result.is_error:
                            failure = ToolExecutionError("mcp_tool_error", "MCP 工具返回业务错误", value=value)
                except MCPError as error:
                    if error.code == REQUEST_TIMEOUT:
                        failure = ToolExecutionError("mcp_timeout", "MCP 请求超时，动作结果需核实")
                    elif error.code == CONNECTION_CLOSED:
                        failure = ToolExecutionError("mcp_result_unknown", "MCP 连接中断，动作结果未知")
                    else:
                        failure = ToolExecutionError(
                            "mcp_protocol_error", "MCP 服务返回协议错误", value={"code": error.code}
                        )
                except (TimeoutError, httpx2.TimeoutException):
                    failure = ToolExecutionError("mcp_timeout", "MCP 请求超时，动作结果需核实")
                except (ValueError, RuntimeError):
                    failure = ToolExecutionError("mcp_invalid_result", "MCP 未返回有效工具结果，动作结果需核实")
        except MCPClientError:
            failure = ToolExecutionError(
                "mcp_result_unknown" if submitted else "mcp_unavailable",
                "MCP 请求中断，动作结果未知" if submitted else "MCP 客户端不可用，请求未提交",
            )
        if failure is not None:
            raise failure
        self.output_state.set(self.ctx, request, value)


class _Factory:
    def __init__(self, bridge: "MCPTools", connection_id: str, remote_name: str, timeout: float) -> None:
        self.bridge, self.connection_id, self.remote_name = bridge, connection_id, remote_name
        self.timeout = timeout

    async def __call__(
        self,
        *,
        ctx: Context,
        storage: StorageService,
        instance_id: str,
        input_state: StateBinding,
        output_state: StateBinding,
        config: dict[str, JsonValue],
    ) -> ToolInstance:
        if ctx is not self.bridge.ctx or not self.bridge.prepared:
            raise ValueError("MCP 工具工厂只用于已完成发现的同一宿主")
        if config:
            raise ValueError("MCP 工具实例不接受额外配置；连接与远程名称由 MCP 声明选择")
        tool = _Tool(
            self.bridge.clients, self.connection_id, self.remote_name, self.timeout, ctx, input_state, output_state
        )
        return ToolInstance(
            ExecutionPlug(
                COMPONENT, tool.execute, {"input": input_state, "output": output_state}, instance_id=instance_id
            ),
            tool.close,
        )


class MCPTools:
    """prepare 完整发现并原子登记工具；同一总表只装配一次，目录变化须重建宿主。

    本地名称由配置显式指定，模型名称和公共 ID 不依赖远端顺序或字符替换。
    tools/list_changed 不修改运行中的工具定义。组件必须先于工具消费者准备。
    """

    def __init__(
        self,
        registry: DefinitionRegistry,
        ctx: Context,
        hooks: HookConnections,
        clients: MCPClients,
        *,
        instance_id: str = "aurora_adapters/mcp/tools",
    ) -> None:
        if not instance_id or not instance_id.strip():
            raise ValueError("MCP 工具桥实例身份不能为空")
        self.registry, self.ctx, self.hooks, self.clients = registry, ctx, hooks, clients
        self.instance_id = instance_id
        self.prepared = False
        self._connected = False

    def component(self, *, depends_on: tuple[str, ...] = ()) -> LifecycleComponent:
        """声明客户端依赖，不访问网络；bot components 的 depends_on 应引用本组件。"""
        if self._connected or self.prepared:
            raise RuntimeError("MCP 工具桥已连接或完成准备")
        entry = entry_from(self.prepare, provider="aurora_adapters.mcp.tools")
        self.hooks.connect(
            PREPARE, entry.id, slot_instance=self.instance_id, handler_instance=self.instance_id, target=self.prepare
        )
        self._connected = True
        return LifecycleComponent(
            self.instance_id, depends_on=tuple(dict.fromkeys((self.clients.instance_id, *depends_on)))
        )

    async def _discover(self, connection_id: str) -> dict[str, Tool]:
        catalog: dict[str, Tool] = {}
        async with self.clients.connection(connection_id) as client:
            if client.server_capabilities.tools is None:
                raise MCPClientError("missing_tools_capability")
            cursor = None
            seen: set[str] = set()
            for _ in range(100):
                page = await client.session.list_tools(params=PaginatedRequestParams(cursor=cursor))
                for tool in page.tools:
                    if tool.name in catalog:
                        raise MCPClientError("duplicate_remote_tool")
                    catalog[tool.name] = tool
                cursor = page.next_cursor
                if cursor is None:
                    return catalog
                if cursor in seen:
                    raise MCPClientError("repeated_tools_cursor")
                seen.add(cursor)
            raise MCPClientError("tools_page_limit")

    @hook_handler("org.aurora.adapters:handlers/mcp/tools/prepare", slot=PREPARE)
    async def prepare(self) -> None:
        if self.prepared:
            raise RuntimeError("MCP 工具已登记；工具集合变化须重建宿主")
        servers = configured_servers(cast(dict, MCP_CONFIG.parse(self.ctx.get(CONFIG_STATE))))
        selections = []
        for connection_id, server in servers.items():
            tools = server["tools"]
            if tools["include"] == ["*"] or any(
                name not in tools["aliases"] for name in tools["include"] if name not in tools["exclude"]
            ):
                raise MCPClientError("unsupported_tool_selection", location=f"servers.{connection_id}.tools")
            selections.extend(
                {"connection_id": connection_id, "remote_name": name, "name": tools["aliases"][name]}
                for name in tools["include"]
                if name not in tools["exclude"]
            )
        catalogs = {}
        for connection_id, server in servers.items():
            if not server["tools"]["include"] and not server["tools"]["exclude"]:
                continue
            async with asyncio.timeout(server["timeout"]["catalog"]):
                catalogs[connection_id] = await self._discover(connection_id)
            if any(
                name not in catalogs[connection_id]
                for name in [*server["tools"]["include"], *server["tools"]["exclude"]]
            ):
                raise MCPClientError("selected_tool_missing")
        entries = []
        for selection in selections:
            remote = catalogs[selection["connection_id"]].get(selection["remote_name"])
            if remote is None:
                raise MCPClientError("selected_tool_missing")
            spec = ToolSpec(
                COMPONENT,
                {"name": selection["name"], "description": remote.description or "", "parameters": remote.input_schema},
                factory=_Factory(
                    self,
                    selection["connection_id"],
                    selection["remote_name"],
                    servers[selection["connection_id"]]["timeout"]["execution"],
                ),
            )
            entries.append(
                RegistryEntry(
                    Id(f"org.aurora.adapters:tools/mcp/{selection['name']}"),
                    "tool",
                    spec,
                    "aurora_adapters.mcp.tools",
                    register_to=TOOLS,
                )
            )
        self.registry.register_many(entries)
        self.prepared = True


def plugin() -> Plugin:
    """声明工具执行组件和发现入口；启用插件本身不创建连接或发现工具。"""
    return Plugin(
        "aurora_adapters.mcp.tools",
        (
            *component_entries(COMPONENT, _Tool, _Tool.execute, provider="aurora_adapters.mcp.tools"),
            entry_from(MCPTools.prepare, provider="aurora_adapters.mcp.tools"),
        ),
        requires=("aurora_adapters.mcp", "aurora_agent.tools"),
    )
