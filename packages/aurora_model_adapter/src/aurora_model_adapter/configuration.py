"""模型 profile 配置与角色引用；运行时工厂和凭证不进入 ctx。"""

from dataclasses import dataclass
from typing import NotRequired, TypedDict, cast

from aurora_core.ids import Id
from aurora_core.json_data import encode_json
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


def validate_config(value: object) -> None:
    encode_json(value)
    if not isinstance(value, dict):
        raise TypeError("模型配置必须为命名配置映射")
    for name, profile in value.items():
        if not name or not isinstance(profile, dict):
            raise ValueError("模型配置名称不能为空，配置必须为对象")
        if not {"adapter", "model"} <= profile.keys() or profile.keys() - {
            "adapter",
            "model",
            "base_url",
            "credential",
            "provider",
            "capabilities",
        }:
            raise ValueError("模型配置仅接受 adapter、model、base_url、credential、provider、capabilities；前两项必填")
        if any(not isinstance(item, str) or not item.strip() for key, item in profile.items() if key != "capabilities"):
            raise ValueError("模型配置字段必须为非空字符串")
        if "capabilities" in profile:
            capabilities = profile["capabilities"]
            if (
                not isinstance(capabilities, dict)
                or set(capabilities) != {"streaming", "tool_calls"}
                or any(type(item) is not bool for item in capabilities.values())
            ):
                raise ValueError("capabilities 必须显式声明 streaming 和 tool_calls 布尔能力")
        Id(profile["adapter"])


def validate_bindings(value: object) -> None:
    encode_json(value)
    if not isinstance(value, dict) or any(
        not role or not isinstance(name, str) or not name for role, name in value.items()
    ):
        raise ValueError("模型绑定必须为非空角色名称到配置名称的映射")


@dataclass(frozen=True)
class ResolvedModel:
    """根据公开 adapter 定义解析出的运行时工厂及其非秘密配置。"""

    profile_name: str
    factory: ModelFactory
    config: ModelConfig
    credential: str | None


def resolve_model(registry: DefinitionRegistry, profiles: object, bindings: object, role: str) -> ResolvedModel:
    """只解析已登记适配器，不导入配置提供的模块路径，也不创建或缓存客户端。"""
    validate_config(profiles)
    validate_bindings(bindings)
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
