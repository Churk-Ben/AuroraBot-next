"""配置声明、通用校验和 config 阶段服务。"""

from .declarations import CONFIGS, ConfigSpec, config_entries
from .schema import ConfigSchema
from .service import configuration_component, load_configuration, plugin
from .templates import ConfigTemplate, copy_missing, read_toml

__all__ = [
    "CONFIGS",
    "ConfigSchema",
    "ConfigSpec",
    "ConfigTemplate",
    "config_entries",
    "configuration_component",
    "copy_missing",
    "load_configuration",
    "plugin",
    "read_toml",
]
