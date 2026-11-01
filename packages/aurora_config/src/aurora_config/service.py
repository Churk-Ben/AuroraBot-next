"""在 config 阶段收集声明、校验全部配置并原子注入 ctx。"""

from copy import deepcopy
from pathlib import Path

from aurora_core import entry_from, hook_handler
from aurora_core.ctx import Context, StateAddress, StateKey, StateRecord
from aurora_core.discovery import Plugin
from aurora_core.hooks import HookConnections
from aurora_core.ids import Id
from aurora_core.lifecycle import CONFIG, LifecycleComponent
from aurora_core.registry import DefinitionRegistry, RegistryEntry
from aurora_core.storage import StorageService

from .declarations import CONFIGS, ConfigReceiver, ConfigSpec
from .templates import checked_path, copy_missing, read_toml


def load_configuration(registry: DefinitionRegistry, directory: Path) -> tuple[StateRecord, ...]:
    """全部文件和配置关系通过校验才返回；用户文件不被覆盖。"""
    root = directory.resolve()
    sources = []
    destinations: set[str] = set()
    states: set[Id] = set()
    for entry in registry.view(register_to=CONFIGS):
        reason = ConfigReceiver().rejection_reason(entry)
        if reason is not None:
            raise ValueError(f"{entry.id}：{reason}")
        spec = entry.target
        assert isinstance(spec, ConfigSpec)
        state = registry.get(spec.state)
        if state.kind != "state_key" or not isinstance(state.target, StateKey) or state.target.persistent:
            raise ValueError(f"配置目标必须为非持久状态：{spec.state}")
        template = spec.template
        source = template.source()
        target = checked_path(
            root / (template.owner or spec.state.namespace) / template.resource.removeprefix("config.tomls/")
        )
        identity = str(target).casefold()
        if identity in destinations or spec.state in states:
            raise ValueError(f"配置目标文件或状态重复：{entry.id}")
        destinations.add(identity)
        states.add(spec.state)
        sources.append((spec, source, target))
    records = []
    for spec, source, target in sources:
        copy_missing(target, source.read_bytes())
        try:
            value = spec.schema.parse(read_toml(target))
        except (ValueError, TypeError) as error:
            raise ValueError(f"配置文件 {target}：{error}") from None
        records.append(StateRecord(StateAddress(spec.state), value))
    values = {record.address.key: record.value for record in records}
    for spec, _, target in sources:
        if spec.check is not None:
            try:
                spec.check(deepcopy(values))
            except (ValueError, TypeError, KeyError) as error:
                raise ValueError(f"配置文件 {target} 的关联校验失败：{error}") from None
    return tuple(records)


class ConfigurationService:
    def __init__(self, registry: DefinitionRegistry, ctx: Context, storage: StorageService) -> None:
        self.registry, self.ctx, self.storage = registry, ctx, storage

    @hook_handler("org.aurora.config:handlers/load", slot=CONFIG)
    def configure(self) -> None:
        self.ctx.configure(load_configuration(self.registry, self.storage.configuration_directory()))


def configuration_component(
    registry: DefinitionRegistry, ctx: Context, hooks: HookConnections, storage: StorageService
) -> LifecycleComponent:
    """宿主显式装配一个配置服务；需要读取配置的 config 处理器应依赖此组件。"""
    registry.get(CONFIGS)
    service = ConfigurationService(registry, ctx, storage)
    entry = entry_from(service.configure, provider="aurora_config")
    owner = "aurora_config"
    hooks.connect(CONFIG, entry.id, slot_instance=owner, handler_instance=owner, target=service.configure)
    return LifecycleComponent(owner)


def plugin() -> Plugin:
    return Plugin(
        "aurora_config",
        (
            RegistryEntry(
                CONFIGS,
                "registry",
                ConfigReceiver(),
                "aurora_config",
                register_to=Id("org.aurora.core:registries/registries"),
            ),
            entry_from(ConfigurationService.configure, provider="aurora_config"),
        ),
    )
