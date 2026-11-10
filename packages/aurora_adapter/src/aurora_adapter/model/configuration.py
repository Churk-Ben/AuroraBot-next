"""模型 profile 配置与角色引用；运行时工厂和凭证不进入 ctx。"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, NotRequired, TypedDict, cast

from aurora_config import ConfigSchema
from aurora_core.ids import Id
from aurora_core.registry import DefinitionRegistry

from .decisions import ChoiceFactory
from .embeddings import EmbeddingFactory
from .models import ModelCapabilities, ModelConfig, ThinkingConfig
from .protocols import ModelFactory

ADAPTERS = Id("org.aurora.adapter:registries/model/adapters")
CHOICE_ADAPTERS = Id("org.aurora.adapter:registries/model/choice_adapters")
EMBEDDING_ADAPTERS = Id("org.aurora.adapter:registries/model/embedding_adapters")
CONFIG = Id("org.aurora.adapter:state/model/config")
BINDINGS = Id("org.aurora.adapter:state/model/bindings")


class ModelProfile(TypedDict):
    """credential 为运行期凭证引用名称，不允许保存 api_key。"""

    adapter: str
    model: str
    base_url: NotRequired[str]
    credential: NotRequired[str]
    provider: NotRequired[str]
    capabilities: NotRequired[dict[str, bool]]
    thinking: NotRequired[ThinkingConfig]
    reasoning_effort: NotRequired[str]


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
                "thinking": {
                    "type": "object",
                    "required": ["type"],
                    "additionalProperties": False,
                    "properties": {
                        "type": {"enum": ["enabled", "disabled"]},
                        "budget_tokens": {"type": "integer", "minimum": 1024},
                    },
                },
                "reasoning_effort": {"enum": ["none", "minimal", "low", "medium", "high", "xhigh", "max"]},
                "capabilities": {
                    "type": "object",
                    "required": ["streaming", "tool_calls"],
                    "additionalProperties": False,
                    "properties": {
                        "streaming": {"type": "boolean"},
                        "tool_calls": {"type": "boolean"},
                        "file_input": {"type": "boolean"},
                    },
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


@dataclass(frozen=True)
class ResolvedChoice:
    """类型化决策模型工厂，与聊天模型使用同一份 profile 和角色绑定。"""

    profile_name: str
    factory: ChoiceFactory
    config: ModelConfig
    credential: str | None


@dataclass(frozen=True)
class ResolvedEmbedding:
    """向量模型工厂及公开索引身份；凭证变更不改变向量空间。"""

    profile_name: str
    factory: EmbeddingFactory
    config: ModelConfig
    credential: str | None
    adapter: str


def resolve_embedding(registry: DefinitionRegistry, profiles: object, bindings: object, role: str) -> ResolvedEmbedding:
    name, profile, config = _profile(profiles, bindings, role)
    entry = registry.get(Id(profile["adapter"]))
    if entry.kind != "adapter" or entry.register_to != EMBEDDING_ADAPTERS or not callable(entry.target):
        raise TypeError("向量配置目标必须为 embedding_adapters 注册表中的可调用工厂")
    if config.capabilities is not None or config.thinking is not None or config.reasoning_effort is not None:
        raise ValueError("向量模型不接受聊天能力或思考配置")
    return ResolvedEmbedding(
        name, cast(EmbeddingFactory, entry.target), config, profile.get("credential"), str(entry.id)
    )


def resolve_model(registry: DefinitionRegistry, profiles: object, bindings: object, role: str) -> ResolvedModel:
    """只解析已登记适配器，不导入配置提供的模块路径，也不创建或缓存客户端。"""
    name, profile, config = _profile(profiles, bindings, role)
    entry = registry.get(Id(profile["adapter"]))
    if entry.kind != "adapter" or entry.register_to != ADAPTERS or not callable(entry.target):
        raise TypeError("模型配置目标必须为 adapters 注册表中的可调用工厂")
    return ResolvedModel(name, cast(ModelFactory, entry.target), config, profile.get("credential"))


def resolve_choice(registry: DefinitionRegistry, profiles: object, bindings: object, role: str) -> ResolvedChoice:
    """只接受 choice 注册表中的工厂，防止将决策端点当作聊天端点。"""
    name, profile, config = _profile(profiles, bindings, role)
    entry = registry.get(Id(profile["adapter"]))
    if entry.kind != "adapter" or entry.register_to != CHOICE_ADAPTERS or not callable(entry.target):
        raise TypeError("决策配置目标必须为 choice_adapters 注册表中的可调用工厂")
    return ResolvedChoice(name, cast(ChoiceFactory, entry.target), config, profile.get("credential"))


def _profile(profiles: object, bindings: object, role: str) -> tuple[str, ModelProfile, ModelConfig]:
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
    capabilities = profile.get("capabilities")
    return (
        name,
        profile,
        ModelConfig(
            profile["model"],
            profile.get("base_url"),
            provider=profile.get("provider"),
            capabilities=None if capabilities is None else ModelCapabilities(**capabilities),
            thinking=profile.get("thinking"),
            reasoning_effort=cast(Any, profile.get("reasoning_effort")),
        ),
    )
