"""模型 profile 配置与角色引用；运行时工厂和凭证不进入 ctx。"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import NotRequired, TypedDict, cast

from aurora_config import ConfigSchema
from aurora_core.ids import Id
from aurora_core.registry import DefinitionRegistry

from .models import ModelCapabilities, ModelConfig
from .protocols import ModelFactory

ADAPTERS = Id("org.aurora.model_adapter:registries/adapters")
CONFIG = Id("org.aurora.model_adapter:state/config")
BINDINGS = Id("org.aurora.model_adapter:state/bindings")


class ModelProfile(TypedDict):
    """credential 为运行期凭证引用名称，不允许保存 api_key。"""

    adapter: str
    model: str
    base_url: NotRequired[str]
    credential: NotRequired[str]
    provider: NotRequired[str]
    capabilities: NotRequired[dict[str, bool]]


_TEXT = {"type": "string", "pattern": r"\S"}
PROFILE_SCHEMA = ConfigSchema(
    {
        "type": "object",
        "propertyNames": {"minLength": 1},
        "additionalProperties": {
            "type": "object",
            "required": ["adapter", "model"],
            "additionalProperties": False,
            "properties": {
                "adapter": {"type": "string", "format": "aurora-id"},
                "model": _TEXT,
                "base_url": _TEXT,
                "credential": _TEXT,
                "provider": _TEXT,
                "capabilities": {
                    "type": "object",
                    "required": ["streaming", "tool_calls"],
                    "additionalProperties": False,
                    "properties": {"streaming": {"type": "boolean"}, "tool_calls": {"type": "boolean"}},
                },
            },
        },
    }
)
BINDINGS_SCHEMA = ConfigSchema(
    {
        "type": "object",
        "propertyNames": {"minLength": 1},
        "additionalProperties": {"type": "string", "minLength": 1},
    }
)


def check_bindings(values: Mapping[Id, object]) -> None:
    profiles = cast(dict, values[CONFIG])
    bindings = cast(dict, values[BINDINGS])
    if any(name not in profiles for name in bindings.values()):
        raise ValueError("模型绑定引用了不存在的配置")


@dataclass(frozen=True)
class ResolvedModel:
    """根据公开 adapter 定义解析出的运行时工厂及其非秘密配置。"""

    profile_name: str
    factory: ModelFactory
    config: ModelConfig
    credential: str | None


def resolve_model(registry: DefinitionRegistry, profiles: object, bindings: object, role: str) -> ResolvedModel:
    """只解析已登记适配器，不导入配置提供的模块路径，也不创建或缓存客户端。"""
    PROFILE_SCHEMA.validate(profiles)
    BINDINGS_SCHEMA.validate(bindings)
    profiles = cast(dict[str, ModelProfile], profiles)
    bindings = cast(dict[str, str], bindings)
    if role not in bindings:
        raise ValueError(f"模型角色未绑定：{role}")
    if any(name not in profiles for name in bindings.values()):
        raise ValueError("模型绑定引用了不存在的配置")
    name = bindings[role]
    profile = profiles[name]
    entry = registry.get(Id(profile["adapter"]))
    if entry.kind != "adapter" or entry.register_to != ADAPTERS or not callable(entry.target):
        raise TypeError("模型配置目标必须为 adapters 注册表中的可调用工厂")
    capabilities = profile.get("capabilities")
    return ResolvedModel(
        name,
        cast(ModelFactory, entry.target),
        ModelConfig(
            profile["model"],
            profile.get("base_url"),
            provider=profile.get("provider"),
            capabilities=None if capabilities is None else ModelCapabilities(**capabilities),
        ),
        profile.get("credential"),
    )
