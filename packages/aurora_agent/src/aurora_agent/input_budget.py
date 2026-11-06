"""按完整交流段选择模型请求历史，不修改持久消息或拆散工具往返。"""

from copy import deepcopy

from aurora_adapter.model import ModelRequest
from aurora_core.json_data import encode_json


class ModelInputBudgetExceeded(ValueError):
    """固定输入和当前交流段无法放入预算；异常只包含长度，不包含业务内容。"""

    def __init__(self, max_chars: int, required_chars: int) -> None:
        self.max_chars, self.required_chars = max_chars, required_chars
        super().__init__(f"模型输入预算不足：至少需要 {required_chars} 字符，预算为 {max_chars}")


class ModelInputBudget:
    """限制统一 ModelRequest JSON 字符数，不等同于供应商 token 或 HTTP 字节数。

    system、临时观察及工具定义完整保留。仅从历史开头移除以无工具调用的
    assistant 消息结束的完整交流段；至少保留最新一段及其后的全部输入和结果。
    省略提示计入预算，不生成摘要，不修改原请求或持久历史。
    """

    def __init__(self, max_chars: int) -> None:
        if type(max_chars) is not int or max_chars < 1024:
            raise ValueError("完整模型输入预算必须为至少 1024 的整数")
        self.max_chars = max_chars

    def apply(self, request: ModelRequest, *, history_start: int) -> ModelRequest:
        if len(encode_json(request)) <= self.max_chars:
            return request
        messages = request["messages"]
        history = messages[history_start:]
        # 最后一条之前的完整回复构成可删除边界，最新交流段始终保留。
        boundaries = [
            index + 1
            for index, message in enumerate(history[:-1])
            if message["role"] == "assistant" and not message.get("tool_calls")
        ]

        def candidate_at(removed: int) -> ModelRequest:
            notice = {
                "kind": "input_budget",
                "omitted_messages": removed,
                "notice": "较早的完整交流段因输入预算省略；持久历史未删除，不代表事项已完成。",
            }
            candidate = deepcopy(request)
            candidate["messages"] = [
                *messages[:history_start],
                {"role": "user", "content": encode_json(notice)},
                *history[removed:],
            ]
            return candidate

        required = len(encode_json(request))
        if not boundaries:
            raise ModelInputBudgetExceeded(self.max_chars, required)
        smallest = candidate_at(boundaries[-1])
        smallest_size = len(encode_json(smallest))
        if smallest_size > self.max_chars:
            raise ModelInputBudgetExceeded(self.max_chars, min(required, smallest_size))
        low, high = 0, len(boundaries) - 1
        while low < high:
            middle = (low + high) // 2
            if len(encode_json(candidate_at(boundaries[middle]))) <= self.max_chars:
                high = middle
            else:
                low = middle + 1
        return candidate_at(boundaries[low])
