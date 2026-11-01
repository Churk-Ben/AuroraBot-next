"""插件声明包内 TOML 模板，宿主按拥有者收集用户配置。"""

import tomllib
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

from .ids import validate_namespace

if TYPE_CHECKING:
    from .ctx import StateRecord
    from .registry import DefinitionRegistry


@dataclass(frozen=True)
class ConfigTemplate:
    """resource 为 config.toml 或 config.tomls/ 下的 TOML 相对路径。"""

    package: str
    resource: str = "config.toml"
    owner: str | None = None

    def __post_init__(self) -> None:
        path = PurePosixPath(self.resource)
        if (
            not self.package
            or "\\" in self.resource
            or path.is_absolute()
            or any(part in ("", ".", "..") or ":" in part for part in self.resource.split("/"))
            or path.suffix != ".toml"
            or not (self.resource == "config.toml" or (len(path.parts) > 1 and path.parts[0] == "config.tomls"))
        ):
            raise ValueError("配置模板必须指向包内 config.toml 或 config.tomls/ 下的 TOML 文件")
        if self.owner is not None:
            validate_namespace(self.owner)


def load_configuration(registry: "DefinitionRegistry", directory: Path) -> tuple["StateRecord", ...]:
    """仅复制缺失文件，读取显式声明的配置；保留文件注释与已有用户内容。"""
    from .ctx import StateAddress, StateKey, StateRecord

    root = directory.resolve()
    sources = []
    destinations: set[str] = set()
    for entry in registry.view(kind="state_key"):
        definition = entry.target
        if not isinstance(definition, StateKey) or definition.config is None:
            continue
        template = definition.config
        package = files(template.package)
        if package.joinpath("config.toml").is_file() and package.joinpath("config.tomls").is_dir():
            raise ValueError(f"配置模板不能同时提供 config.toml 与 config.tomls：{template.package}")
        source = package.joinpath(*PurePosixPath(template.resource).parts)
        if not source.is_file():
            raise ValueError(f"配置模板不存在：{template.package}/{template.resource}")
        relative = template.resource.removeprefix("config.tomls/")
        target = root / (template.owner or entry.id.namespace) / relative
        if target.resolve() != target or not target.resolve().is_relative_to(root):
            raise ValueError(f"配置路径存在重定向或超出配置目录：{target}")
        identity = str(target).casefold()
        if identity in destinations:
            raise ValueError(f"配置目标文件重复：{target}")
        destinations.add(identity)
        sources.append((entry.id, source, target))
    records = []
    for key, source, target in sources:
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            with target.open("xb") as stream:
                stream.write(source.read_bytes())
        except FileExistsError:
            pass
        try:
            value = tomllib.loads(target.read_text(encoding="utf-8-sig"))
        except (tomllib.TOMLDecodeError, UnicodeError):
            raise ValueError(f"TOML 配置无法解析：{target}") from None
        records.append(StateRecord(StateAddress(key), value))
    return tuple(records)
