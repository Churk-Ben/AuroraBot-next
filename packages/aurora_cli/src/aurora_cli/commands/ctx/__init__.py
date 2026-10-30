"""ctx 命令声明与结果输出，实际状态操作由 core 完成。"""

from typing import TextIO

from aurora_core.ctx import StateAddress
from aurora_core.json_data import encode_json

KEY = {"name": "key", "type": "id"}
WHERE = {"name": "location", "type": "location", "option": True}
DEFINITIONS = {
    "ctx/get": {"help": "读取精确状态地址", "arguments": [KEY, WHERE]},
    "ctx/set": {"help": "以 JSON 整项替换状态", "arguments": [KEY, {"name": "value", "type": "json"}, WHERE]},
    "ctx/delete": {"help": "删除精确状态地址", "arguments": [KEY, WHERE]},
    "ctx/list": {"help": "枚举已赋值地址", "arguments": [{**KEY, "option": True}, WHERE]},
    "ctx/watch": {"help": "观察当前宿主后续变化，Ctrl+C 退出", "arguments": [{**KEY, "option": True}, WHERE]},
}
for name, spec in DEFINITIONS.items():
    if name != "ctx/watch":
        spec["operation"] = f"org.aurora.core:operations/{name}"


def address_data(address: StateAddress) -> dict[str, object]:
    return {"id": str(address.key), "location": dict(address.location)}


def write_json(output: TextIO, value: object) -> None:
    print(encode_json(value), file=output, flush=True)


def render_result(output: TextIO, name: str, result: object) -> None:
    if name == "ctx/list":
        if not isinstance(result, tuple) or any(not isinstance(item, StateAddress) for item in result):
            raise TypeError("ctx/list 必须返回状态地址元组")
        result = [address_data(item) for item in result]
    write_json(output, result)
