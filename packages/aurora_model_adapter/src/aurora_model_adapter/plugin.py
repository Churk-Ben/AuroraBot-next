"""登记当前实现的模型协议入口；工厂及实例由装配显式选择。"""

from aurora_core.bootstrap import KindReceiver
from aurora_core.ctx import StateKey
from aurora_core.discovery import Plugin
from aurora_core.ids import Id
from aurora_core.registry import RegistryEntry

from .configuration import validate_bindings, validate_config
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
        ("state/config", "state_key", StateKey(validate_config), "state_keys"),
        ("state/bindings", "state_key", StateKey(validate_bindings), "state_keys"),
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
        ),
    )
