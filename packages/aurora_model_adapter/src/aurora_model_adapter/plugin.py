"""登记当前实现的模型协议入口；工厂及实例由装配显式选择。"""

from aurora_config import ConfigSpec, ConfigTemplate, config_entries
from aurora_core.bootstrap import KindReceiver
from aurora_core.discovery import Plugin
from aurora_core.ids import Id
from aurora_core.registry import RegistryEntry

from .adapters import create_litellm
from .configuration import BINDINGS, BINDINGS_SCHEMA, CONFIG, PROFILE_SCHEMA, check_bindings
from .models import ModelCapabilities, ModelChunk, ModelRequest, ModelResponse
from .protocols import ModelClient


def plugin() -> Plugin:
    definitions = (
        ("registries/adapters", "registry", KindReceiver(frozenset({"adapter"})), "registries"),
        ("services/model_client", "service", ModelClient, "services"),
        ("schemas/model_request", "schema", ModelRequest, "schemas"),
        ("schemas/model_response", "schema", ModelResponse, "schemas"),
        ("schemas/model_chunk", "schema", ModelChunk, "schemas"),
        ("schemas/model_capabilities", "schema", ModelCapabilities, "schemas"),
    )
    return Plugin(
        "aurora_model_adapter",
        tuple(
            RegistryEntry(
                Id(f"org.aurora.model_adapter:{path}"),
                kind,
                target,
                "aurora_model_adapter",
                register_to=Id(f"org.aurora.core:registries/{receiver}"),
            )
            for path, kind, target, receiver in definitions
        )
        + (
            *config_entries(
                Id("org.aurora.model_adapter:configs/profiles"),
                ConfigSpec(
                    CONFIG, ConfigTemplate("aurora_model_adapter", "config.tomls/profiles.toml"), PROFILE_SCHEMA
                ),
                provider="aurora_model_adapter",
            ),
            *config_entries(
                Id("org.aurora.model_adapter:configs/bindings"),
                ConfigSpec(
                    BINDINGS,
                    ConfigTemplate("aurora_model_adapter", "config.tomls/bindings.toml"),
                    BINDINGS_SCHEMA,
                    check=check_bindings,
                ),
                provider="aurora_model_adapter",
            ),
            RegistryEntry(
                Id("org.aurora.model_adapter:adapters/litellm"),
                "adapter",
                create_litellm,
                "aurora_model_adapter",
                register_to=Id("org.aurora.model_adapter:registries/adapters"),
            ),
        ),
        requires=("aurora_config",),
    )
