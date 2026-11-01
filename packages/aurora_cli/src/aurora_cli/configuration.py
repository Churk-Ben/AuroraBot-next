"""插件发现前读取宿主 TOML；仅在启动本地宿主时创建缺失模板。"""

import tomllib
from importlib.resources import files
from pathlib import Path

from aurora_core.ids import Id


def read_host_config(root: Path) -> dict[str, object]:
    path = root.resolve() / "config" / "host.toml"
    if path.resolve() != path:
        raise ValueError(f"宿主配置路径存在重定向：{path}")
    if not path.exists():
        return {}
    try:
        value = tomllib.loads(path.read_text(encoding="utf-8-sig"))
    except (tomllib.TOMLDecodeError, UnicodeError):
        raise ValueError(f"宿主 TOML 无法解析：{path}") from None
    if value.keys() - {"plugins", "assembly"}:
        raise ValueError("host.toml 仅支持 plugins 和 assembly")
    plugins = value.get("plugins", [])
    if not isinstance(plugins, list) or any(not isinstance(name, str) or not name.strip() for name in plugins):
        raise ValueError("host.toml 的 plugins 必须为插件名称列表")
    if "assembly" in value:
        Id(value["assembly"])
    return value


def initialize_host_config(directory: Path) -> None:
    path = directory.resolve() / "host.toml"
    if path.resolve() != path:
        raise ValueError(f"宿主配置路径存在重定向：{path}")
    try:
        with path.open("xb") as stream:
            stream.write(files("aurora_cli").joinpath("host.toml").read_bytes())
    except FileExistsError:
        pass
