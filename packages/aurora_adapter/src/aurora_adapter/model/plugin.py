"""登记当前实现的模型协议入口；工厂及实例由装配显式选择。"""

from aurora_config import ConfigSpec, ConfigTemplate, config_entries
from aurora_core.bootstrap import KindReceiver
from aurora_core.discovery import Plugin
from aurora_core.ids import Id
from aurora_core.registry import RegistryEntry

from .adapters import create_litellm
from .configuration import BINDINGS, BINDINGS_SCHEMA, CONFIG, PROFILE_SCHEMA, check_bindings
from .decisions import ChoiceClient, create_litellm_choice
from .embeddings import EmbeddingClient, create_openai_embedding
from .models import ModelCapabilities, ModelChunk, ModelRequest, ModelResponse
from .protocols import ModelClient


def plugin() -> Plugin:
    definitions = (
        ("registries/model/adapters", "registry", KindReceiver(frozenset({"adapter"})), "registries"),
        ("registries/model/choice_adapters", "registry", KindReceiver(frozenset({"adapter"})), "registries"),
        ("registries/model/embedding_adapters", "registry", KindReceiver(frozenset({"adapter"})), "registries"),
        ("services/model/embedding_client", "service", EmbeddingClient, "services"),
        ("services/model/choice_client", "service", ChoiceClient, "services"),
        ("services/model/client", "service", ModelClient, "services"),
        ("schemas/model/request", "schema", ModelRequest, "schemas"),
        ("schemas/model/response", "schema", ModelResponse, "schemas"),
        ("schemas/model/chunk", "schema", ModelChunk, "schemas"),
        ("schemas/model/capabilities", "schema", ModelCapabilities, "schemas"),
    )
    return Plugin(
        "aurora_adapter.model",
        tuple(
            RegistryEntry(
                Id(f"org.aurora.adapter:{path}"),
                kind,
                target,
                "aurora_adapter.model",
                register_to=Id(f"org.aurora.core:registries/{receiver}"),
            )
            for path, kind, target, receiver in definitions
        )
        + (
            RegistryEntry(
                Id("org.aurora.adapter:adapters/model/openai_embedding"),
                "adapter",
                create_openai_embedding,
                "aurora_adapter.model",
                register_to=Id("org.aurora.adapter:registries/model/embedding_adapters"),
            ),
            *config_entries(
                Id("org.aurora.adapter:configs/model/profiles"),
                ConfigSpec(
                    CONFIG, ConfigTemplate("aurora_adapter", "config.tomls/model/profiles.toml"), PROFILE_SCHEMA
                ),
                provider="aurora_adapter.model",
            ),
            *config_entries(
                Id("org.aurora.adapter:configs/model/bindings"),
                ConfigSpec(
                    BINDINGS,
                    ConfigTemplate("aurora_adapter", "config.tomls/model/bindings.toml"),
                    BINDINGS_SCHEMA,
                    check=check_bindings,
                ),
                provider="aurora_adapter.model",
            ),
            RegistryEntry(
                Id("org.aurora.adapter:adapters/model/litellm_choice"),
                "adapter",
                create_litellm_choice,
                "aurora_adapter.model",
                register_to=Id("org.aurora.adapter:registries/model/choice_adapters"),
            ),
            RegistryEntry(
                Id("org.aurora.adapter:adapters/model/litellm"),
                "adapter",
                create_litellm,
                "aurora_adapter.model",
                register_to=Id("org.aurora.adapter:registries/model/adapters"),
            ),
        ),
        requires=("aurora_config",),
    )
