"""显式汇总内置命令，仅登记元数据。"""

from aurora_core.bootstrap import REGISTRY_DIRECTORY
from aurora_core.ctx import StateKey
from aurora_core.ids import Id
from aurora_core.registry import DefinitionRegistry, RegistryEntry

from ..declarations import COMMANDS, CONFIG, CommandReceiver
from . import about, check, ctx, donk, help, run


def install_commands(registry: DefinitionRegistry) -> None:
    """登记命令接收方、描述格式、配置状态及内置命令。"""
    definitions = {
        **help.DEFINITIONS,
        **ctx.DEFINITIONS,
        **run.DEFINITIONS,
        **about.DEFINITIONS,
        **donk.DEFINITIONS,
        **check.DEFINITIONS,
    }
    entries = [
        RegistryEntry(COMMANDS, "registry", CommandReceiver(), "aurora_cli", register_to=REGISTRY_DIRECTORY),
        RegistryEntry(
            Id("org.aurora.cli:schemas/command"),
            "schema",
            {"help": "string", "operation": "完整操作 ID", "arguments": "name/type/option/required 参数列表"},
            "aurora_cli",
            register_to=Id("org.aurora.core:registries/schemas"),
        ),
        RegistryEntry(
            CONFIG, "state_key", StateKey(), "aurora_cli", register_to=Id("org.aurora.core:registries/state_keys")
        ),
    ]
    for name, spec in definitions.items():
        entries.append(
            RegistryEntry(Id(f"org.aurora.cli:commands/{name}"), "command", spec, "aurora_cli", register_to=COMMANDS)
        )
    registry.register_many(entries)
