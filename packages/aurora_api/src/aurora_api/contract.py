"""本机 ctx 传输的公开数据描述；不读取登记表、配置或运行期资源。"""

from .protocol import CHANGED, HTTP_ACTIONS, SUBSCRIBE, UNSUBSCRIBE, WATCH_PATH


def _ref(name: str) -> dict:
    return {"$ref": f"#/$defs/{name}"}


def _object(properties: dict, required: tuple[str, ...] | None = None) -> dict:
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties if required is None else required),
        "additionalProperties": False,
    }


def describe_contract() -> dict:
    """返回独立的 JSON Schema 与显式绑定；业务状态值只声明为 JSON。"""
    filters = {"key": _ref("StateId"), "location": _ref("Location")}
    definitions = {
        "JsonValue": {
            "anyOf": [
                {"type": "null"},
                {"type": "boolean"},
                {"type": "number"},
                {"type": "string"},
                {"type": "array", "items": _ref("JsonValue")},
                {"type": "object", "additionalProperties": _ref("JsonValue")},
            ]
        },
        "StateId": {"type": "string", "format": "aurora-id"},
        "Location": {
            "type": "object",
            "propertyNames": {"minLength": 1},
            "additionalProperties": {"type": "string", "minLength": 1},
        },
        "StateAddress": _object({"id": _ref("StateId"), "location": _ref("Location")}),
        "GetRequest": _object(filters, ("key",)),
        "ListRequest": _object(filters, ()),
        "SetRequest": _object({**filters, "value": _ref("JsonValue")}, ("key", "value")),
        "DeleteRequest": _object(filters, ("key",)),
        "WatchRequest": _object(filters, ()),
        "GetResponse": _object({"result": _ref("JsonValue")}),
        "ListResponse": _object({"result": {"type": "array", "items": _ref("StateAddress")}}),
        "SetResponse": _object({"result": {"type": "null"}}),
        "DeleteResponse": _object({"result": {"type": "boolean"}}),
        "ApiError": _object({"code": {"type": "string"}, "message": {"type": "string"}}),
        "ErrorResponse": _object({"error": _ref("ApiError")}),
        "StateChange": _object(
            {
                "id": _ref("StateId"),
                "location": _ref("Location"),
                "revision": {"type": "integer", "minimum": 1},
                "action": {"enum": ["set", "delete"]},
                "value": _ref("JsonValue"),
                "previous": _ref("JsonValue"),
                "existed": {"type": "boolean"},
            }
        ),
        "WatchReady": _object({"type": {"const": "ready"}}),
        "WatchEvent": _object({"type": {"const": "event"}, "event": {"const": CHANGED}, "data": _ref("StateChange")}),
        "WatchError": _object({"type": {"const": "error"}, "error": _ref("ApiError")}),
        "WatchMessage": {"anyOf": [_ref("WatchReady"), _ref("WatchEvent"), _ref("WatchError")]},
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$defs": definitions,
        "http": {
            action: {
                "method": "POST",
                "path": path,
                "operation": str(operation),
                "request": _ref(f"{action.title()}Request"),
                "response": _ref(f"{action.title()}Response"),
                "error": _ref("ErrorResponse"),
            }
            for action, (path, operation) in HTTP_ACTIONS.items()
        },
        "watch": {
            "path": WATCH_PATH,
            "subscribe": str(SUBSCRIBE),
            "unsubscribe": str(UNSUBSCRIBE),
            "event": CHANGED,
            "request": _ref("WatchRequest"),
            "message": _ref("WatchMessage"),
            "subscription": "one_per_connection",
            "unsubscribe_by": "close_connection",
            "revision_scope": "host_context",
            "replay": False,
            "reconnect": "resubscribe_then_refresh",
        },
    }
