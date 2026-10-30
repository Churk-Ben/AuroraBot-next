"""控制连接交换状态地址，执行请求仅携带身份信息。"""

import logging
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from uuid import uuid4

from aurora_core.ctx import Context, StateAddress
from aurora_core.hooks import HookConnection, HookConnections
from aurora_core.ids import Id

CHILDREN = Id("org.aurora.bot:control/children")
EXECUTE = Id("org.aurora.bot:handlers/control/execute")
CONTROL_STATE = Id("org.aurora.bot:state/control")
_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExecutionRequest:
    """一次调用的身份；同一运行的每次迭代、分支调用均生成新的 execution_id。"""

    run_id: str
    execution_id: str = field(default_factory=lambda: uuid4().hex)
    parent_execution_id: str | None = None

    def child(self) -> "ExecutionRequest":
        return ExecutionRequest(self.run_id, parent_execution_id=self.execution_id)


@dataclass(frozen=True)
class StateBinding:
    """握手时交换的业务状态位置；按 run_id 定位，结构和并发写入由组件约定。

    同一运行内重复调用可更新同一业务位置。需要保留每次调用结果的组件自行增加
    execution_id 定位；控制完成通过等待调用判断，不读取旧结果来推断完成。
    """

    key: Id
    location: tuple[tuple[str, str], ...] = ()

    def address(self, request: ExecutionRequest) -> StateAddress:
        return StateAddress(self.key, tuple(sorted(dict(self.location, run_id=request.run_id).items())))

    def get(self, ctx: Context, request: ExecutionRequest) -> object:
        address = self.address(request)
        return ctx.get(address.key, location=dict(address.location))

    def set(self, ctx: Context, request: ExecutionRequest, value: object) -> None:
        address = self.address(request)
        ctx.set(address.key, value, location=dict(address.location))


@dataclass(frozen=True)
class ExecutionPlug:
    """实例执行插头；states/schema 用于连接，调用只接收身份并等待完成。"""

    instance_id: str
    execute: Callable[[ExecutionRequest], Awaitable[None]]
    states: Mapping[str, StateBinding] = field(default_factory=dict)
    schema: object | None = None

    async def __call__(self, request: ExecutionRequest) -> None:
        await self.execute(request)


@dataclass(frozen=True)
class ExecutionLink:
    """连接双方的地址描述；装配可将此握手结果交给任一方保存。"""

    connection: HookConnection
    plug: ExecutionPlug
    slot_states: Mapping[str, StateBinding]
    slot_schema: object | None


class ExecutionSlot:
    """实例插槽自行判断兼容；没有 schema 时允许依赖双方的代码约定。

    accept 返回拒绝原因或 None。schema 是接收方解释的描述，不提供全局比较算法；
    未提供 accept 表示接收遵循 ExecutionPlug 调用约定的连接。
    """

    def __init__(
        self,
        instance_id: str,
        hooks: HookConnections,
        *,
        states: Mapping[str, StateBinding] | None = None,
        schema: object | None = None,
        accept: Callable[[ExecutionPlug], str | None] | None = None,
    ) -> None:
        self.instance_id = instance_id
        self.hooks = hooks
        self.states = dict(states or {})
        self.schema = schema
        self.accept = accept
        self._links: dict[HookConnection, ExecutionLink] = {}

    def connect(self, plug: ExecutionPlug, *, priority: int = 0) -> ExecutionLink:
        """校验后建立 core 实例连接，不执行组件、不读写业务状态。"""
        if self.accept is not None and (reason := self.accept(plug)) is not None:
            raise ValueError(f"插槽 {self.instance_id} 拒绝 {plug.instance_id}：{reason}")
        connection = self.hooks.connect(
            CHILDREN,
            EXECUTE,
            slot_instance=self.instance_id,
            handler_instance=plug.instance_id,
            target=plug,
            priority=priority,
        )
        link = ExecutionLink(connection, plug, dict(self.states), self.schema)
        self._links[connection] = link
        if self.schema is not None and plug.schema is not None and self.schema != plug.schema:
            _logger.warning("插槽 %s 接受了描述不同但兼容的插头 %s", self.instance_id, plug.instance_id)
        return link

    def links(self) -> tuple[ExecutionLink, ...]:
        """以 core 的显式连接顺序获取当前子组件，断开的连接不参与执行。"""
        return tuple(self._links[item] for item in self.hooks.for_slot(CHILDREN, self.instance_id))

    async def invoke(self, link: ExecutionLink, request: ExecutionRequest) -> None:
        await self.hooks.invoke(link.connection, request)
