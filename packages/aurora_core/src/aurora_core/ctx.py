"""共享内存状态的显式访问；运行时服务应使用装配引用。"""

import inspect
from collections.abc import Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass
from threading import get_ident
from typing import Literal

from .events import Event, EventBus
from .ids import Id
from .registry import DefinitionRegistry, RegistryEntry

CTX_CHANGED = Id("org.aurora.core:events/ctx/changed")


@dataclass(frozen=True)
class StateKey:
    """状态定义的可选同步校验器；通过时返回 None，拒绝时抛出异常。

    状态值须为支持独立深拷贝的数据。校验器收到独立副本，不通过返回值转换数据。
    """

    validate: Callable[[object], None] | None = None

    def __post_init__(self) -> None:
        if self.validate is not None and (not callable(self.validate) or inspect.iscoroutinefunction(self.validate)):
            raise TypeError("状态校验器必须是同步回调")


@dataclass(frozen=True)
class StateAddress:
    """完整业务地址；location 是排序后的非空字符串键值对，不表示权限边界。"""

    key: Id
    location: tuple[tuple[str, str], ...] = ()


def _location(location: Mapping[str, str] | None) -> tuple[tuple[str, str], ...]:
    if location is None:
        return ()
    for key, value in location.items():
        if not isinstance(key, str) or not key or not isinstance(value, str) or not value:
            raise ValueError("业务定位字段和值必须为非空字符串")
    return tuple(sorted(location.items()))


@dataclass(frozen=True)
class StateChange:
    """已提交的整项变更；existed 区分原值为空与原状态不存在。"""

    address: StateAddress
    revision: int
    action: Literal["set", "delete"]
    value: object
    previous: object
    existed: bool


class Context:
    """仅在创建线程访问的共享状态，适用于单宿主事件循环。

    get/set 均复制数据；set 整项替换，同值写入也产生新修订。缺失读取抛出 KeyError，
    缺失删除返回 False。原语同步提交，同线程协程按调用顺序生效；读改写组合不构成事务。
    业务定位精确匹配，不回退至全局状态。跨线程工作须将访问调度回宿主线程。
    """

    def __init__(self, registry: DefinitionRegistry) -> None:
        self._registry = registry
        self._owner = get_ident()
        self._closed = False
        self._validating = False
        self._values: dict[StateAddress, object] = {}
        self._revision = 0
        self._events = EventBus()

    def _check_open(self) -> None:
        if get_ident() != self._owner:
            raise RuntimeError("ctx 接口必须在创建它的宿主线程调用")
        if self._closed:
            raise RuntimeError("ctx 已关闭")

    def _definition(self, key: Id) -> StateKey:
        if not isinstance(key, Id):
            raise TypeError("状态项身份必须为 Id")
        entry = self._registry.get(key)
        if entry.kind != "state_key" or not isinstance(entry.target, StateKey):
            raise TypeError(f"目标不是 StateKey 状态定义：{key}")
        return entry.target

    def get(self, key: Id, *, location: Mapping[str, str] | None = None) -> object:
        """读取精确地址的独立副本；缺失定义或状态均抛出 KeyError。"""
        self._check_open()
        self._definition(key)
        return deepcopy(self._values[StateAddress(key, _location(location))])

    def set(self, key: Id, value: object, *, location: Mapping[str, str] | None = None) -> None:
        """校验成功后整项替换；复制或校验失败不提交，也不通知。"""
        self._check_open()
        if self._validating:
            raise RuntimeError("校验期间不得修改 ctx")
        definition = self._definition(key)
        address = StateAddress(key, _location(location))
        self._validating = True
        try:
            candidate = deepcopy(value)
            if definition.validate is not None:
                result = definition.validate(deepcopy(candidate))
                if inspect.iscoroutine(result):
                    result.close()
                if result is not None:
                    raise TypeError("状态校验器通过时必须返回 None")
            change = StateChange(
                address,
                self._revision + 1,
                "set",
                deepcopy(candidate),
                deepcopy(self._values.get(address)),
                address in self._values,
            )
        finally:
            self._validating = False
        self._values[address] = candidate
        self._revision = change.revision
        self._events.publish(CTX_CHANGED, change)

    def delete(self, key: Id, *, location: Mapping[str, str] | None = None) -> bool:
        """删除一个精确地址；不存在时返回 False，不产生修订或通知。"""
        self._check_open()
        if self._validating:
            raise RuntimeError("校验期间不得修改 ctx")
        self._definition(key)
        address = StateAddress(key, _location(location))
        if address not in self._values:
            return False
        change = StateChange(address, self._revision + 1, "delete", None, deepcopy(self._values[address]), True)
        del self._values[address]
        self._revision = change.revision
        self._events.publish(CTX_CHANGED, change)
        return True

    def list(self, *, key: Id | None = None, location: Mapping[str, str] | None = None) -> tuple[StateAddress, ...]:
        """按完整 ID 与定位字段排序枚举已赋值地址，不返回值或未赋值定义。

        location=None 不过滤业务地址，空字典只选择全局地址；非空字典精确匹配。
        """
        self._check_open()
        if key is not None:
            self._definition(key)
        selected = None if location is None else _location(location)
        return tuple(
            sorted(
                (
                    address
                    for address in self._values
                    if (key is None or address.key == key) and (selected is None or address.location == selected)
                ),
                key=lambda address: (str(address.key), address.location),
            )
        )

    def subscribe(
        self,
        callback: Callable[[StateChange], None],
        *,
        key: Id | None = None,
        location: Mapping[str, str] | None = None,
    ) -> str:
        """订阅后续变化，不补发历史；过滤规则与 list 一致，回调须同步。"""
        self._check_open()
        if key is not None:
            self._definition(key)
        if not callable(callback) or inspect.iscoroutinefunction(callback):
            raise TypeError("状态监听器必须是同步回调")
        selected = None if location is None else _location(location)

        def notify(event: Event) -> None:
            change = event.payload
            if not isinstance(change, StateChange):
                raise TypeError("ctx 变更载荷必须为 StateChange")
            if (key is None or change.address.key == key) and (selected is None or change.address.location == selected):
                return callback(change)

        return self._events.subscribe(notify, event_type=CTX_CHANGED)

    def unsubscribe(self, handle: str) -> bool:
        """取消尚未开始的通知；关闭后仍可幂等取消。"""
        return self._events.unsubscribe(handle)

    def close(self) -> None:
        """释放内存和订阅；宿主必须先完成所需持久化。"""
        if get_ident() != self._owner:
            raise RuntimeError("ctx 接口必须在创建它的宿主线程调用")
        if self._validating:
            raise RuntimeError("校验期间不得关闭 ctx")
        self._closed = True
        self._events.close()
        self._values.clear()


def install_context(registry: DefinitionRegistry) -> Context:
    """将当前 ctx 的六个操作和变化事件登记至总表，重复装配报错。"""
    ctx = Context(registry)
    registry.register_many(
        [
            *(
                RegistryEntry(
                    Id(f"org.aurora.core:operations/ctx/{name}"),
                    "operation",
                    getattr(ctx, name),
                    "aurora_core",
                    register_to=Id("org.aurora.core:registries/operations"),
                )
                for name in ("get", "set", "delete", "list", "subscribe", "unsubscribe")
            ),
            RegistryEntry(
                CTX_CHANGED, "event", StateChange, "aurora_core", register_to=Id("org.aurora.core:registries/events")
            ),
        ]
    )
    return ctx
