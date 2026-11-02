"""来源工厂登记、固定身份的接纳入口及宿主生命周期绑定。"""

from collections.abc import Awaitable, Callable
from copy import deepcopy
from dataclasses import dataclass
from functools import partial
from threading import get_ident
from typing import Protocol

from aurora_core import entry_from, hook_handler
from aurora_core.bootstrap import Receiver
from aurora_core.ctx import Context
from aurora_core.hooks import HookConnections
from aurora_core.ids import Id
from aurora_core.json_data import encode_json
from aurora_core.lifecycle import CLEAN, PREPARE, START, STOP, LifecycleComponent
from aurora_core.registry import RegistryEntry

from .records import WorldReceipt, WorldRecords, _identity

SOURCES = Id("org.aurora.world:registries/sources")


class SourceUnavailableError(RuntimeError):
    """来源尚未开放或已停止接纳，消息未写入记录。"""


class SourceEmit(Protocol):
    """只在宿主线程同步提交；来源身份由装配绑定，回执只表示内存接纳。"""

    def __call__(self, *, message_id: str, payload: object) -> WorldReceipt: ...


@dataclass(frozen=True)
class SourceInstance:
    """来源的异步生命周期动作；start 返回表示启动完成，不等待来源整个寿命。

    stop 必须结束自有任务，aclose 释放资源；失败后相应动作须能再次调用。
    工厂返回前的失败和取消由工厂清理，返回后资源交给 WorldSources 托管。
    """

    start: Callable[[], Awaitable[None]]
    stop: Callable[[], Awaitable[None]]
    aclose: Callable[[], Awaitable[None]]

    def __post_init__(self) -> None:
        if not all(callable(action) for action in (self.start, self.stop, self.aclose)):
            raise TypeError("来源实例必须提供可调用的 start/stop/aclose")


class SourceFactory(Protocol):
    """prepare 阶段创建来源；不接收原始 ctx，运行时共享资源通过装配注入。"""

    async def __call__(self, *, source_id: str, emit: SourceEmit, config: dict[str, object]) -> SourceInstance: ...


@dataclass(frozen=True)
class SourceSpec:
    """来源定义；登记与接入诊断只检查声明，不调用工厂。"""

    factory: SourceFactory

    def __post_init__(self) -> None:
        if not callable(self.factory):
            raise TypeError("来源工厂必须可调用")


class SourceReceiver:
    def rejection_reason(self, entry: RegistryEntry) -> str | None:
        return None if entry.kind == "source" and isinstance(entry.target, SourceSpec) else "来源登记需要 SourceSpec"


@dataclass
class _Binding:
    source_id: str
    factory: SourceFactory
    config: dict[str, object]
    instance: SourceInstance | None = None
    accepting: bool = False
    started: bool = False
    stopped: bool = False


class WorldSources:
    """一个宿主的来源所有者；同一 ctx 的来源应由同一对象装配。

    add 选择定义并绑定唯一 source_id；component 只连接现有生命周期插槽。
    进入各来源 start 时开放其入口，启动失败立即关闭全部入口；已接纳记录不撤销。
    stop_accepting 永久封闭入口，不因重试清理而重新开放；重新启动需新建宿主所有者。
    插件内代码并非安全隔离，固定回调只约束正常接口使用，不阻止恶意 Python 反射。
    """

    def __init__(self, ctx: Context, hooks: HookConnections, *, instance_id: str = "aurora_world/sources") -> None:
        _identity(instance_id)
        self._ctx, self._hooks = ctx, hooks
        self._records = WorldRecords(ctx)
        self._instance_id = instance_id
        self._owner = get_ident()
        self._bindings: dict[str, _Binding] = {}
        self._connected = False
        self._prepare_called = False
        self._prepared = False
        self._start_called = False
        self._quiesced = False

    def _check_owner(self) -> None:
        if get_ident() != self._owner:
            raise RuntimeError("来源接口必须在创建它的宿主线程调用")

    def add(self, identity: Id, *, source_id: str, config: dict[str, object] | None = None) -> None:
        """准备前选择一个来源；source_id 在本所有者内唯一，配置必须为 JSON 对象。"""
        self._check_owner()
        if self._prepare_called or self._quiesced:
            raise RuntimeError("来源已经开始准备或停止，不接受新的装配")
        _identity(source_id)
        if source_id in self._bindings:
            raise ValueError("来源实例身份重复")
        receiver = self._ctx.registry.get(SOURCES)
        if receiver.kind != "registry" or not isinstance(receiver.target, Receiver):
            raise ValueError("未登记 world 来源接收方")
        entry = self._ctx.registry.get(identity)
        if entry.register_to != SOURCES or entry.kind != "source" or not isinstance(entry.target, SourceSpec):
            raise ValueError("目标不是已登记的世界来源")
        reason = receiver.target.rejection_reason(entry)
        if reason is not None:
            raise ValueError(f"来源接入被拒绝：{reason}")
        values = {} if config is None else config
        if type(values) is not dict:
            raise TypeError("来源配置必须为 JSON 对象")
        encode_json(values)
        self._bindings[source_id] = _Binding(source_id, entry.target.factory, deepcopy(values))

    def component(self, *, depends_on: tuple[str, ...] = ()) -> LifecycleComponent:
        """连接来源所有者的生命周期；不创建来源、任务或状态。"""
        self._check_owner()
        if self._connected or self._prepare_called or self._quiesced:
            raise RuntimeError("来源生命周期已连接或不再允许装配")
        links = []
        try:
            for phase, method in ((PREPARE, self.prepare), (START, self.start), (STOP, self.stop), (CLEAN, self.clean)):
                entry = entry_from(method, provider="aurora_world")
                links.append(
                    self._hooks.connect(
                        phase,
                        entry.id,
                        slot_instance=self._instance_id,
                        handler_instance=self._instance_id,
                        target=method,
                    )
                )
        except Exception:
            for link in links:
                self._hooks.disconnect(link)
            raise
        self._connected = True
        return LifecycleComponent(self._instance_id, depends_on=depends_on, stop_accepting=self.stop_accepting)

    def _emit(self, binding: _Binding, *, message_id: str, payload: object) -> WorldReceipt:
        self._check_owner()
        if not binding.accepting or self._quiesced:
            raise SourceUnavailableError("来源尚未启动或已经停止接纳")
        return self._records.append(source_id=binding.source_id, message_id=message_id, payload=payload)

    @hook_handler("org.aurora.world:handlers/sources/prepare", slot=PREPARE)
    async def prepare(self) -> None:
        self._check_owner()
        if self._prepare_called or self._quiesced:
            raise RuntimeError("来源不能重复准备或在停止后准备")
        self._prepare_called = True
        try:
            for binding in self._bindings.values():
                instance = await binding.factory(
                    source_id=binding.source_id, emit=partial(self._emit, binding), config=deepcopy(binding.config)
                )
                if not isinstance(instance, SourceInstance):
                    raise TypeError("来源工厂必须返回 SourceInstance")
                binding.instance = instance
                if self._quiesced:
                    raise SourceUnavailableError("来源准备期间已停止接纳")
        except BaseException:
            self.stop_accepting()
            raise
        self._prepared = True

    @hook_handler("org.aurora.world:handlers/sources/start", slot=START)
    async def start(self) -> None:
        self._check_owner()
        if not self._prepared or self._start_called or self._quiesced:
            raise RuntimeError("来源尚未准备、已经启动或已经停止")
        self._start_called = True
        try:
            for binding in self._bindings.values():
                if self._quiesced:
                    raise SourceUnavailableError("来源启动期间已停止接纳")
                assert binding.instance is not None
                binding.accepting = binding.started = True
                await binding.instance.start()
                if self._quiesced:
                    raise SourceUnavailableError("来源启动期间已停止接纳")
        except BaseException:
            self.stop_accepting()
            raise

    def stop_accepting(self) -> None:
        """同步且幂等封闭所有入口，包括来源已保留的回调。"""
        self._check_owner()
        self._quiesced = True
        for binding in self._bindings.values():
            binding.accepting = False

    @hook_handler("org.aurora.world:handlers/sources/stop", slot=STOP)
    async def stop(self) -> None:
        self.stop_accepting()
        for binding in reversed(tuple(self._bindings.values())):
            if binding.instance is not None and binding.started and not binding.stopped:
                await binding.instance.stop()
                binding.stopped = True

    @hook_handler("org.aurora.world:handlers/sources/clean", slot=CLEAN)
    async def clean(self) -> None:
        self.stop_accepting()
        for binding in reversed(tuple(self._bindings.values())):
            if binding.instance is not None:
                if binding.started and not binding.stopped:
                    raise RuntimeError("来源任务尚未停止，不能释放资源")
                await binding.instance.aclose()
                binding.instance = None
