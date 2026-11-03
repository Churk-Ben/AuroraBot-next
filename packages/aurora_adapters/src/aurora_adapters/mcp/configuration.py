"""MCP v2 声明；配置校验不访问环境变量、文件系统或网络。"""

import re
from collections.abc import Callable
from typing import cast
from urllib.parse import urlsplit

from aurora_config import ConfigSchema
from aurora_core import Id

CONFIGURATION = Id("org.aurora.adapters:configs/mcp")
CONFIG_STATE = Id("org.aurora.adapters:state/mcp/config")
CLIENT_STATUS = Id("org.aurora.adapters:state/mcp/clients")
PROTOCOL_VERSION = "2026-07-28"
CAPABILITIES = ("tools", "resources", "prompts", "completions")
SERVER_NAME = r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}(?![\s\S])"
TOOL_NAME = r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*(?![\s\S])"
ENV_NAME = r"^[A-Za-z_][A-Za-z0-9_]*(?![\s\S])"
TIMEOUTS = {"startup": 10, "catalog": 30, "execution": 30, "shutdown": 10}
_REFERENCE = re.compile(r"\{env:([A-Za-z_][A-Za-z0-9_]*)\}")
_HEADER_NAME = re.compile(r"^[!#$%&'*+.^_|~0-9A-Za-z-]+$")
_CONTROL_HEADERS = {"accept", "content-type", "host", "content-length", "transfer-encoding", "connection", "upgrade"}
_CREDENTIAL_HEADERS = {"authorization", "proxy-authorization", "cookie", "x-api-key", "api-key"}
_CREDENTIAL_ENV = re.compile(r"(?:^|_)(?:TOKEN|SECRET|PASSWORD|API_KEY|APIKEY|ACCESS_KEY)$", re.IGNORECASE)


def validate_url(value: str) -> None:
    """地址不可携带凭证、查询串、片段或环境占位符。"""
    try:
        url = urlsplit(value)
        valid = (
            url.scheme in ("http", "https")
            and url.hostname
            and url.port != 0
            and not (url.username or url.password or url.query or url.fragment)
            and "@" not in url.netloc
            and "{env" not in value
            and not any(character.isspace() or ord(character) < 32 for character in value)
        )
    except ValueError:
        valid = False
    if not valid:
        raise ValueError("MCP 地址须为无凭证、查询串、片段及环境占位符的 HTTP(S) URL")


def _check_reference(value: str, *, credential: bool = False) -> None:
    if "{env" in _REFERENCE.sub("", value):
        raise ValueError("MCP 环境引用须为 {env:NAME}")
    if credential and not _REFERENCE.search(value):
        raise ValueError("MCP 凭证字段必须使用环境引用")


def resolve_values(values: dict[str, str], resolver: Callable[[str], str | None], *, headers: bool) -> dict[str, str]:
    """仅在创建资源时展开引用；失败只返回字段名，不携带声明或解析值。"""
    result = {}
    for key, value in values.items():

        def replace(match: re.Match) -> str:
            resolved = resolver(match[1])
            if not resolved or not resolved.strip():
                raise ValueError("环境引用不可用")
            return resolved

        try:
            resolved = _REFERENCE.sub(replace, value)
            if "\0" in resolved or (
                headers and (not resolved.isascii() or any(ord(c) < 32 or ord(c) == 127 for c in resolved))
            ):
                raise ValueError(key)
        except Exception:  # noqa: BLE001 — 自定义解析器也不得通过异常泄露凭证。
            raise ValueError(key) from None
        result[key] = resolved
    return result


def _check_servers(value: object) -> None:
    aliases = set()
    for name, server in cast(dict, value)["servers"].items():
        if server["type"] == "remote":
            validate_url(server["url"])
            seen = set()
            for key, content in server.get("headers", {}).items():
                lower = key.lower()
                if (
                    not _HEADER_NAME.fullmatch(key)
                    or lower in seen
                    or lower in _CONTROL_HEADERS
                    or lower.startswith("mcp-")
                ):
                    raise ValueError(f"MCP 服务 {name} 的 headers 名称冲突、非法或由协议管理")
                seen.add(lower)
                _check_reference(content, credential=lower in _CREDENTIAL_HEADERS)
                if not content.isascii() or any(ord(c) < 32 or ord(c) == 127 for c in content):
                    raise ValueError(f"MCP 服务 {name} 的 headers 值含非法字符")
            if server.get("oauth", False) is not False:
                raise ValueError(f"MCP 服务 {name}: unsupported_auth")
        else:
            for part in [*server["command"], server.get("cwd", ".")]:
                if "\0" in part or "{env" in part:
                    raise ValueError(f"MCP 服务 {name} 的 command/cwd 不接受 NUL 或环境引用")
            if not server["command"][0].strip() or not server.get("cwd", ".").strip():
                raise ValueError(f"MCP 服务 {name} 的 command/cwd 不能为空")
            for key, content in server.get("environment", {}).items():
                _check_reference(content, credential=bool(_CREDENTIAL_ENV.search(key)))
                if "\0" in content:
                    raise ValueError(f"MCP 服务 {name} 的 environment 含 NUL")
        tools = server["tools"]
        if "*" in tools["include"] and tools["include"] != ["*"]:
            raise ValueError("MCP 工具通配项须独占 include")
        for remote, alias in tools["aliases"].items():
            if remote in tools["exclude"] or (tools["include"] != ["*"] and remote not in tools["include"]):
                raise ValueError("MCP 别名必须引用已选择的工具")
            if server["enabled"]:
                if alias in aliases:
                    raise ValueError("MCP 工具本地名称重复")
                aliases.add(alias)


def configured_servers(config: dict) -> dict[str, dict]:
    """为已解析声明合并超时，保持服务身份；禁用项不成为运行资源。"""
    return {
        name: {**server, "connection_id": name, "timeout": {**TIMEOUTS, **config["timeout"], **server["timeout"]}}
        for name, server in config["servers"].items()
        if server["enabled"]
    }


def _timeout_schema() -> dict:
    return {
        "type": "object",
        "additionalProperties": False,
        "default": {},
        "properties": {
            key: {"type": "number", "exclusiveMinimum": 0, "maximum": maximum}
            for key, maximum in {"startup": 300, "catalog": 3600, "execution": 43200, "shutdown": 300}.items()
        },
    }


class _MCPConfigSchema(ConfigSchema):
    def parse(self, value: object) -> object:
        if isinstance(value, dict) and ("connections" in value or "tools" in value):
            raise ValueError("MCP 旧版或混合配置须显式迁移：python -m aurora_adapters.mcp.migrate")
        return super().parse(value)


MCP_CONFIG = _MCPConfigSchema(
    {
        "type": "object",
        "additionalProperties": False,
        "required": ["schema_version"],
        "properties": {
            "schema_version": {"type": "integer", "const": 2},
            "timeout": _timeout_schema(),
            "servers": {
                "type": "object",
                "default": {},
                "propertyNames": {"pattern": SERVER_NAME},
                "additionalProperties": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["type"],
                    "properties": {
                        "type": {"enum": ["remote", "local"]},
                        "enabled": {"type": "boolean", "default": True},
                        "protocol": {"enum": ["legacy", "auto", PROTOCOL_VERSION], "default": "legacy"},
                        "required_capabilities": {
                            "type": "array",
                            "uniqueItems": True,
                            "default": [],
                            "items": {"enum": list(CAPABILITIES)},
                        },
                        "timeout": _timeout_schema(),
                        "url": {"type": "string", "minLength": 1},
                        "headers": {"type": "object", "additionalProperties": {"type": "string"}},
                        "oauth": {},
                        "command": {"type": "array", "minItems": 1, "items": {"type": "string"}},
                        "cwd": {"type": "string", "minLength": 1},
                        "environment": {
                            "type": "object",
                            "propertyNames": {"pattern": ENV_NAME},
                            "additionalProperties": {"type": "string"},
                        },
                        "tools": {
                            "type": "object",
                            "additionalProperties": False,
                            "default": {},
                            "properties": {
                                "include": {
                                    "type": "array",
                                    "uniqueItems": True,
                                    "default": ["*"],
                                    "items": {"type": "string", "minLength": 1},
                                },
                                "exclude": {
                                    "type": "array",
                                    "uniqueItems": True,
                                    "default": [],
                                    "items": {"type": "string", "minLength": 1, "not": {"const": "*"}},
                                },
                                "aliases": {
                                    "type": "object",
                                    "default": {},
                                    "propertyNames": {"minLength": 1, "not": {"const": "*"}},
                                    "additionalProperties": {"type": "string", "pattern": TOOL_NAME, "maxLength": 64},
                                },
                            },
                        },
                    },
                    "allOf": [
                        {
                            "if": {"properties": {"type": {"const": "remote"}}},
                            "then": {
                                "required": ["url"],
                                "properties": {key: False for key in ("command", "cwd", "environment")},
                            },
                        },
                        {
                            "if": {"properties": {"type": {"const": "local"}}},
                            "then": {
                                "required": ["command"],
                                "properties": {key: False for key in ("url", "headers", "oauth")},
                            },
                        },
                    ],
                },
            },
        },
    },
    check=_check_servers,
)
