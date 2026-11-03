"""MCP 连接声明；凭证只允许引用运行期环境变量。"""

from typing import cast
from urllib.parse import urlsplit

from aurora_config import ConfigSchema
from aurora_core import Id

CONFIGURATION = Id("org.aurora.adapters:configs/mcp")
CONFIG_STATE = Id("org.aurora.adapters:state/mcp/config")
CLIENT_STATUS = Id("org.aurora.adapters:state/mcp/clients")
PROTOCOL_VERSION = "2026-07-28"
CAPABILITIES = ("tools", "resources", "prompts", "completions")


def _check_connections(value: object) -> None:
    identities = set()
    for connection in cast(dict, value)["connections"]:
        identity = connection["connection_id"]
        if identity in identities:
            raise ValueError("MCP 连接身份重复")
        identities.add(identity)
        try:
            url = urlsplit(connection["url"])
            valid = (
                url.scheme in ("http", "https")
                and url.hostname
                and url.port != 0
                and not (url.username or url.password or url.query or url.fragment)
                and "@" not in url.netloc
                and not any(character.isspace() or ord(character) < 32 for character in connection["url"])
            )
        except ValueError:
            valid = False
        if not valid:
            raise ValueError("MCP 地址须为无凭证、查询串及片段的 HTTP(S) URL")
    names = set()
    for tool in cast(dict, value)["tools"]:
        if tool["connection_id"] not in identities:
            raise ValueError("MCP 工具引用了未配置的连接")
        if tool["name"] in names:
            raise ValueError("MCP 工具本地名称重复")
        names.add(tool["name"])


MCP_CONFIG = ConfigSchema(
    {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "tools": {
                "type": "array",
                "default": [],
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["connection_id", "remote_name", "name"],
                    "properties": {
                        "connection_id": {"type": "string", "minLength": 1},
                        "remote_name": {"type": "string", "minLength": 1},
                        "name": {"type": "string", "pattern": "^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$", "maxLength": 64},
                    },
                },
            },
            "connections": {
                "type": "array",
                "default": [],
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["connection_id", "url"],
                    "properties": {
                        "connection_id": {"type": "string", "pattern": "^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$"},
                        "url": {"type": "string", "minLength": 1},
                        "required_capabilities": {
                            "type": "array",
                            "uniqueItems": True,
                            "items": {"type": "string", "enum": list(CAPABILITIES)},
                            "default": [],
                        },
                        "connect_timeout": {"type": "number", "exclusiveMinimum": 0, "maximum": 300, "default": 10},
                        "request_timeout": {"type": "number", "exclusiveMinimum": 0, "maximum": 3600, "default": 30},
                        "token_env": {"type": "string", "pattern": "^[A-Za-z_][A-Za-z0-9_]*$"},
                    },
                },
            },
        },
    },
    check=_check_connections,
)
