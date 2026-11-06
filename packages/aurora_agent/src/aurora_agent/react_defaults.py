"""默认 ReAct 阶段：准备上下文、解释模型决定和回填工具观察。"""

from collections.abc import Callable
from typing import TypedDict, cast

from aurora_adapter.model import Message, ModelProtocolError, ModelRequest, ToolCall
from aurora_control import ExecutionLink, ExecutionPlug, ExecutionRequest, InstanceStateBinding, component_entries
from aurora_core.ctx import Context
from aurora_core.discovery import Plugin
from aurora_core.ids import Id
from aurora_core.json_data import encode_json

from .input_budget import ModelInputBudget, ModelInputBudgetExceeded
from .model import ModelCall, ModelCallState
from .react import Guidance, ReActAgent
from .tools import ToolBatchState, ToolExecutor, failure, read_request


class PendingTurn(TypedDict):
    """已产生工具请求但尚未形成完整观察的模型轮次。"""

    run_id: str
    turn_id: str
    message: Message


class ReActContext(TypedDict):
    """上下文及引导消费位置整项写入，避免重复接纳和孤立的工具消息。"""

    messages: list[Message]
    guidance_sequence: int
    pending: PendingTurn | None


class ReActDefaults:
    """将已有 agent、ModelCall 与 ToolExecutor 连接成可使用的默认流程。

    context_state 是实例级 ReActContext，prepare 原子保存消息与已接纳的引导位置。
    引导 payload 为字符串时直接作为 user 内容，其他 JSON 编码后作为环境输入。
    模型文本保留在上下文中，不自动发布为用户消息；无工具请求即允许结束。
    工具请求与全部结果一起回填，普通工具失败仍作为 tool 消息进入下一次推理。
    context_view 在每次 prepare 同步生成临时 user 观察，置于历史之前，不写入 context。

    后续激活遇到 pending 时保留可获得的工具结果，将其余标记 interrupted，
    不自动重跑动作、不假定中断的动作没有副作用。恢复所需的工具输出由装配保留，
    context、inbox 与工具记录的裁剪同样由装配负责。本组件不关闭共享模型客户端。
    """

    def __init__(
        self,
        agent: ReActAgent,
        model: ModelCall,
        tools: ToolExecutor,
        *,
        context_state: InstanceStateBinding,
        system_prompt: str = "",
        context_view: Callable[[ExecutionRequest], str] | None = None,
        input_budget: ModelInputBudget | None = None,
    ) -> None:
        if agent.ctx is not model.ctx or agent.ctx is not tools.ctx:
            raise ValueError("默认 ReAct 组件必须使用同一 ctx")
        if not isinstance(context_state, InstanceStateBinding):
            raise TypeError("ReAct 上下文必须使用实例级绑定")
        self.agent, self.model, self.tools = agent, model, tools
        self.ctx: Context = agent.ctx
        self.context_state, self.system_prompt = context_state, system_prompt
        self.context_view = context_view
        self.input_budget = input_budget

    def connect(self) -> None:
        """连接四个工作阶段；装配须先登记对应插件，失败时撤销本次连接。"""
        phases = ("prepare", "infer", "act", "observe")
        if any(self.agent.slots[phase].links() for phase in phases):
            raise ValueError("默认阶段要求 prepare/infer/act/observe 尚未连接")
        links: list[ExecutionLink] = []
        try:
            for phase, method in (
                ("prepare", "build_prompt"),
                ("infer", "interpret_response"),
                ("observe", "record_observation"),
            ):
                plug = ExecutionPlug(
                    Id(f"org.aurora.agent:handlers/react/{method}"),
                    getattr(self, method),
                    {
                        **self.agent.states,
                        "context": self.context_state,
                        "model_input": self.model.request_state,
                        "model_output": self.model.output_state,
                        "tool_input": self.tools.request_state,
                        "tool_output": self.tools.output_state,
                    },
                    instance_id=f"{self.agent.instance_id}/{method}",
                )
                links.append(self.agent.slots[phase].connect(plug, priority=10))
            links.append(self.agent.slots["infer"].connect(self.model.plug))
            links.append(self.agent.slots["act"].connect(self.tools.plug))
        except Exception:
            for link in links:
                self.agent.slots["prepare"].hooks.disconnect(link.connection)
            raise

    def _context(self, request: ExecutionRequest) -> ReActContext:
        try:
            value = self.context_state.get(self.ctx, request)
        except KeyError:
            return {"messages": [], "guidance_sequence": 0, "pending": None}
        if (
            not isinstance(value, dict)
            or not isinstance(value.get("messages"), list)
            or type(value.get("guidance_sequence")) is not int
            or value["guidance_sequence"] < 0
            or "pending" not in value
        ):
            raise ValueError("ReAct 上下文格式无效")
        return cast(ReActContext, value)

    def _settle(self, context: ReActContext, *, recovering: bool) -> None:
        pending = context["pending"]
        if pending is None:
            if not recovering:
                raise ValueError("没有待接纳的工具轮次")
            return
        calls = pending["message"].get("tool_calls", [])
        try:
            value = self.tools.output_state.get(self.ctx, ExecutionRequest(pending["run_id"]))
        except KeyError:
            value = None
        matching = isinstance(value, dict) and value.get("turn_id") == pending["turn_id"]
        if not recovering and (not matching or cast(dict, value).get("status") != "completed"):
            raise ValueError("工具批次尚未完成或与待接纳轮次不符")
        results = cast(ToolBatchState, value)["results"] if matching else []
        by_id = {result["call_id"]: result for result in results}
        if len(by_id) != len(results):
            raise ValueError("工具结果的调用身份重复")
        observations: list[Message] = []
        for call in calls:
            result = by_id.get(call["id"])
            if result is None:
                if not recovering:
                    raise ValueError("工具批次缺少调用结果")
                result = failure(call, "interrupted", "没有完整工具结果，动作是否完成需核实；未自动重试")
            if result["name"] != call["name"] or result["status"] not in ("completed", "failed", "cancelled"):
                raise ValueError("工具结果与原始请求不符")
            observations.append({"role": "tool", "tool_call_id": call["id"], "content": encode_json(result)})
        context["messages"].extend([pending["message"], *observations])
        context["pending"] = None

    async def build_prompt(self, request: ExecutionRequest) -> None:
        context = self._context(request)
        self._settle(context, recovering=True)
        batch = self.agent.batch.get(self.ctx, request)
        if not isinstance(batch, list):
            raise TypeError("prepare 需要引导 batch 列表")
        for item in cast(list[Guidance], batch):
            if item["sequence"] > context["guidance_sequence"]:
                payload = item["payload"]
                context["messages"].append(
                    {"role": "user", "content": payload if isinstance(payload, str) else encode_json(payload)}
                )
                context["guidance_sequence"] = item["sequence"]
        self.context_state.set(self.ctx, request, context)
        messages = list(context["messages"])
        if self.context_view is not None:
            view = self.context_view(request)
            if not isinstance(view, str):
                raise TypeError("上下文视图必须返回文本")
            if view:
                messages.insert(0, {"role": "user", "content": view})
        if self.system_prompt:
            messages.insert(0, {"role": "system", "content": self.system_prompt})
        model_request: ModelRequest = {"messages": messages}
        definitions = self.tools.definitions()
        if definitions:
            model_request["tools"] = definitions
        if self.input_budget is not None:
            try:
                model_request = self.input_budget.apply(
                    model_request, history_start=len(messages) - len(context["messages"])
                )
            except ModelInputBudgetExceeded:
                address = self.model.request_state.address(request)
                self.ctx.delete(address.key, location=dict(address.location))
                raise
        self.model.request_state.set(self.ctx, request, model_request)

    async def interpret_response(self, request: ExecutionRequest) -> None:
        value = self.model.output_state.get(self.ctx, request)
        if not isinstance(value, dict) or value.get("status") != "completed":
            raise ModelProtocolError("模型尚未完成")
        response = cast(ModelCallState, value)
        calls: list[ToolCall] = response["tool_calls"]
        expected = "tool_calls" if calls else "stop"
        if response["finish_reason"] != expected:
            raise ModelProtocolError("模型没有形成完整且一致的行动决定")
        batch = read_request({"turn_id": response["execution_id"], "calls": calls})
        context = self._context(request)
        if context["pending"] is not None:
            raise ValueError("上一工具轮次尚未接纳")
        message: Message = {"role": "assistant", "content": response["text"]}
        if calls:
            message["tool_calls"] = calls
            context["pending"] = {"run_id": request.run_id, "turn_id": batch["turn_id"], "message": message}
        elif response["text"]:
            context["messages"].append(message)
        self.context_state.set(self.ctx, request, context)
        self.tools.request_state.set(self.ctx, request, batch)
        self.agent.decision.set(self.ctx, request, "act" if calls else "finish")

    async def record_observation(self, request: ExecutionRequest) -> None:
        context = self._context(request)
        self._settle(context, recovering=False)
        self.context_state.set(self.ctx, request, context)


def plugin() -> Plugin:
    return Plugin(
        "aurora_agent.react_defaults",
        tuple(
            entry
            for method in ("build_prompt", "interpret_response", "record_observation")
            for entry in component_entries(
                Id(f"org.aurora.agent:handlers/react/{method}"),
                ReActDefaults,
                getattr(ReActDefaults, method),
                provider="aurora_agent",
            )
        ),
        requires=("aurora_agent.react", "aurora_agent.model", "aurora_agent.tools"),
    )
