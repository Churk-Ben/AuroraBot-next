"""持续巡检工作台：示例内的世界来源、串行调度与默认 bot 联动。"""

import asyncio
import json
import logging
import math
from contextlib import suppress
from dataclasses import replace
from functools import partial
from typing import cast
from uuid import uuid4

from aurora_bot.assembly import DefaultAssembly
from aurora_bot.assembly import plugin as assembly_plugin
from aurora_bot.assembly_config import AGENTS, CONFIG, MESSAGES, RUN, WORK
from aurora_bot.control import CONTROL_STATE, ExecutionPlug, ExecutionRequest, component_entries
from aurora_bot.control import plugin as control_plugin
from aurora_bot.model import plugin as model_plugin
from aurora_bot.react import plugin as react_plugin
from aurora_bot.react_defaults import ReActContext
from aurora_bot.react_defaults import plugin as defaults_plugin
from aurora_bot.tools import TOOLS, ToolInstance, ToolSpec
from aurora_bot.tools import plugin as tools_plugin
from aurora_cli.declarations import CONFIG as CLI_CONFIG
from aurora_core import Id, entry_from, hook_handler
from aurora_core.configuration import ConfigTemplate
from aurora_core.ctx import StateKey
from aurora_core.discovery import Plugin
from aurora_core.lifecycle import PREPARE, START, STOP, LifecycleComponent
from aurora_core.registry import RegistryEntry
from aurora_model_adapter.configuration import ADAPTERS, BINDINGS
from aurora_model_adapter.configuration import CONFIG as MODEL_CONFIG
from aurora_model_adapter.fake import FakeModel, FakeReply
from aurora_model_adapter.plugin import plugin as adapter_plugin
from aurora_world.plugin import plugin as world_plugin
from pipeline import INSPECT, PIPELINE, STEPS, create_inspector, declared

NAMESPACE = "dev.example.workshop"
ASSEMBLY = Id(f"{NAMESPACE}:assemblies/live")
SETTINGS = Id(f"{NAMESPACE}:state/settings")
WORLD = Id(f"{NAMESPACE}:state/world")
REQUEST = Id(f"{NAMESPACE}:state/request")
STATUS = Id(f"{NAMESPACE}:state/status")
REPORTS = Id(f"{NAMESPACE}:state/reports")
ADAPTER = Id(f"{NAMESPACE}:adapters/fake")
INSPECT_TOOL = Id(f"{NAMESPACE}:tools/inspect")
REPORT_TOOL = Id(f"{NAMESPACE}:tools/report")
REPORT = Id(f"{NAMESPACE}:handlers/report")
EXPOSED = (SETTINGS, WORLD, REQUEST, STATUS, REPORTS, PIPELINE, AGENTS, MESSAGES, RUN, WORK, CONTROL_STATE, BINDINGS)
logger = logging.getLogger(__name__)


def settings(value):
    if not isinstance(value, dict) or value.keys() - {"automatic", "interval", "steps", "delay"}:
        raise ValueError("settings 仅接受 automatic、interval、steps、delay")
    result = {"automatic": True, "interval": 8.0, "steps": 3, "delay": 0.3, **value}
    if type(result["automatic"]) is not bool or type(result["steps"]) is not int or not 1 <= result["steps"] <= 20:
        raise ValueError("automatic 必须为布尔值，steps 为 1 至 20 的整数")
    for name, lower, upper in (("interval", 0.5, 3600), ("delay", 0, 2)):
        number = result[name]
        if type(number) not in (int, float) or not math.isfinite(number) or not lower <= number <= upper:
            raise ValueError(f"{name} 必须在 {lower} 至 {upper} 之间")
    return result


def validate_settings(value):
    settings(value)


def validate_request(value):
    if not isinstance(value, dict) or value.keys() - {"text", "fail", "steps"}:
        raise ValueError("request 仅接受 text、fail、steps")
    if not isinstance(value.get("text"), str) or not value["text"].strip():
        raise ValueError("text 必须为非空字符串")
    if type(value.get("fail", False)) is not bool:
        raise ValueError("fail 必须为布尔值")
    settings({"steps": value.get("steps", 3)})


async def create_model(config, *, api_key=None):
    """确定性模型通过正式工具协议决策；保留一个请求样本，适合长时间演示。"""

    def respond(request):
        del model.requests[:-1]
        jobs, calls, observations = {}, {}, []
        for message in request["messages"]:
            if message["role"] == "user":
                job = json.loads(message["content"])
                jobs[job["job_id"]] = job
            elif message["role"] == "assistant":
                calls.update({call["id"]: call for call in message.get("tool_calls", [])})
            elif message["role"] == "tool":
                observations.append(json.loads(message["content"]))
        reported = {call["arguments"]["source"] for call in calls.values() if call["name"] == "publish_report"}
        pending = [item for item in observations if item["name"] == "inspect" and item["call_id"] not in reported]
        if pending:
            return FakeReply(
                ("正在整理巡检结果。",),
                tuple(
                    {
                        "id": uuid4().hex,
                        "name": "publish_report",
                        "arguments": {
                            "source": item["call_id"],
                            "text": calls[item["call_id"]]["arguments"]["text"],
                            "result": item,
                        },
                    }
                    for item in pending
                ),
            )
        processed = {call["arguments"]["job_id"] for call in calls.values() if call["name"] == "inspect"}
        waiting = [job for identity, job in jobs.items() if identity not in processed]
        if waiting:
            return FakeReply(
                ("已接纳任务，", "开始分步巡检。"),
                tuple({"id": uuid4().hex, "name": "inspect", "arguments": job} for job in waiting),
            )
        return FakeReply((config.model, "：本次巡检结束，等待新的环境变化或任务。"))

    model = FakeModel(respond, delay=0.05 if config.model == "fast" else 0.2)
    logger.info("已创建离线模型 %s", config.model)
    return model


async def create_reporter(*, ctx, storage, instance_id, input_state, output_state, config):
    async def execute(request):
        arguments = input_state.get(ctx, request)["arguments"]
        try:
            ledger = storage.get(NAMESPACE, "reports")
        except KeyError:
            ledger = {"total": 0, "recent": []}
        record = {**arguments, "run_id": request.run_id}
        ledger = {"total": ledger["total"] + 1, "recent": [*ledger["recent"], record][-10:]}
        # SQLite 台账是报告的持久化来源，ctx 提供可观察视图。
        storage.set(NAMESPACE, "reports", ledger)
        ctx.set(REPORTS, ledger)
        output_state.set(ctx, request, {"published": ledger["total"]})
        logger.info("报告 #%s：%s（%s）", ledger["total"], arguments["text"], arguments["result"]["status"])

    return ToolInstance(
        ExecutionPlug(REPORT, execute, {"input": input_state, "output": output_state}, instance_id=instance_id)
    )


class Workshop:
    """来源与调度任务各自持有，调度组件停止后才关闭 bot 的工具和模型。"""

    def __init__(self, registry, ctx, hooks, storage):
        self.ctx, self.hooks, self.storage = ctx, hooks, storage
        self.bot = DefaultAssembly(registry=registry, ctx=ctx, hooks=hooks, storage=storage)
        self.wake = asyncio.Event()
        self.changed = asyncio.Event()
        self.source = self.worker = None
        self.subscription = None
        self.closing = self.busy = False

    @hook_handler(f"{NAMESPACE}:handlers/prepare", slot=PREPARE)
    def prepare(self):
        try:
            initial = self.ctx.get(CLI_CONFIG)
        except KeyError:
            initial = {}
        defaults = {
            SETTINGS: settings(initial),
            WORLD: {"tick": 0, "temperature": 20},
            STATUS: {"activations": 0, "status": "idle", "sequence": 0},
        }
        for key, value in defaults.items():
            try:
                self.ctx.get(key)
            except KeyError:
                self.ctx.set(key, value)
        try:
            ledger = self.storage.get(NAMESPACE, "reports")
        except KeyError:
            ledger = {"total": 0, "recent": []}
        self.ctx.set(REPORTS, ledger)
        for key in (PIPELINE, CONTROL_STATE):
            for address in self.ctx.list(key=key):
                self.ctx.delete(key, location=dict(address.location))

    def enqueue(self, data):
        if self.closing:
            return
        request = ExecutionRequest("guidance")
        agent = self.bot.agent
        assert agent is not None
        pending = agent.pending(request)
        state = self.ctx.get(STATUS)
        sequence = state["sequence"] + 1
        current = settings(self.ctx.get(SETTINGS))
        job = {"job_id": uuid4().hex, "steps": current["steps"], "delay": current["delay"], "fail": False, **data}
        agent.inbox.set(self.ctx, request, [*pending, {"sequence": sequence, "id": job["job_id"], "payload": job}])
        self.ctx.set(STATUS, {**state, "sequence": sequence})
        self.wake.set()
        logger.info("已接纳引导 #%s：%s", sequence, job["text"])

    def observe(self, change):
        if change.action != "set" or change.address.location:
            return
        if change.address.key == REQUEST:
            self.enqueue(change.value)
        elif change.address.key == SETTINGS:
            self.changed.set()
        elif change.address.key == WORLD:
            current = settings(self.ctx.get(SETTINGS))
            agent = self.bot.agent
            if (
                current["automatic"]
                and not self.busy
                and agent is not None
                and not agent.pending(ExecutionRequest("poll"))
            ):
                self.enqueue({"text": f"自动巡检 #{change.value['tick']}"})

    @hook_handler(f"{NAMESPACE}:handlers/start_world", slot=START)
    def start_world(self):
        self.source = asyncio.create_task(self.produce(), name="workshop-world")

    async def produce(self):
        while True:
            current = settings(self.ctx.get(SETTINGS))
            world = self.ctx.get(WORLD)
            tick = world["tick"] + 1
            self.ctx.set(WORLD, {"tick": tick, "temperature": 20 + tick % 9})
            self.changed.clear()
            with suppress(TimeoutError):
                await asyncio.wait_for(self.changed.wait(), current["interval"])

    @hook_handler(f"{NAMESPACE}:handlers/start_cadence", slot=START)
    def start_cadence(self):
        self.subscription = self.ctx.subscribe(self.observe)
        self.ctx.set(STATUS, {**self.ctx.get(STATUS), "status": "idle"})
        self.worker = asyncio.create_task(self.schedule(), name="workshop-cadence")
        self.wake.set()

    async def schedule(self):
        while True:
            await self.wake.wait()
            self.wake.clear()
            agent = self.bot.agent
            assert agent is not None
            request = ExecutionRequest(uuid4().hex)
            if not agent.pending(request):
                continue
            self.busy = True
            state = self.ctx.get(STATUS)
            self.ctx.set(
                STATUS,
                {**state, "status": "running", "activations": state["activations"] + 1, "run_id": request.run_id},
            )
            try:
                await self.bot.activate(request)
            except asyncio.CancelledError:
                self.ctx.set(STATUS, {**self.ctx.get(STATUS), "status": "cancelled"})
                raise
            except Exception:
                logger.exception("本次激活失败；宿主继续等待新的输入")
                self.ctx.set(STATUS, {**self.ctx.get(STATUS), "status": "failed"})
            else:
                self.ctx.set(STATUS, {**self.ctx.get(STATUS), "status": "completed"})
                assert self.bot.defaults is not None
                context = cast(ReActContext, self.bot.defaults.context_state.get(self.ctx, request))
                # 保留最近一组引导及其完整工具往返，避免常驻演示无限积累上下文。
                start = max(index for index, message in enumerate(context["messages"]) if message["role"] == "user")
                while start and context["messages"][start - 1]["role"] == "user":
                    start -= 1
                self.bot.defaults.context_state.set(
                    self.ctx, request, {**context, "messages": context["messages"][start:]}
                )
                if agent.pending(request):
                    self.wake.set()
            finally:
                self.busy = False

    def stop_accepting(self):
        self.closing = True

    @hook_handler(f"{NAMESPACE}:handlers/stop_cadence", slot=STOP)
    async def stop_cadence(self):
        if self.subscription is not None:
            self.ctx.unsubscribe(self.subscription)
        if self.worker is not None:
            self.worker.cancel()
            with suppress(asyncio.CancelledError):
                await self.worker

    @hook_handler(f"{NAMESPACE}:handlers/stop_world", slot=STOP)
    async def stop_world(self):
        if self.source is not None:
            self.source.cancel()
            with suppress(asyncio.CancelledError):
                await self.source


def assemble(*, registry, ctx, hooks, storage):
    entry = registry.get(INSPECT_TOOL)
    registry.replace(
        replace(
            entry,
            target=ToolSpec(INSPECT, entry.target.definition, factory=partial(create_inspector, registry=registry)),
        )
    )
    app = Workshop(registry, ctx, hooks, storage)
    for owner, phase, method in (
        ("workshop/settings", PREPARE, app.prepare),
        ("workshop/world", START, app.start_world),
        ("workshop/world", STOP, app.stop_world),
        ("workshop/cadence", START, app.start_cadence),
        ("workshop/cadence", STOP, app.stop_cadence),
    ):
        definition = entry_from(method, provider=NAMESPACE)
        hooks.connect(phase, definition.id, slot_instance=owner, handler_instance=owner, target=method)
    model, bot = app.bot.components()
    return (
        LifecycleComponent("workshop/settings"),
        replace(model, depends_on=("workshop/settings",)),
        bot,
        LifecycleComponent("workshop/world", depends_on=("workshop/settings",), stop_accepting=app.stop_accepting),
        LifecycleComponent(
            "workshop/cadence", depends_on=(bot.instance_id, "workshop/world"), stop_accepting=app.stop_accepting
        ),
    )


def plugins():
    tool_schema = {
        "type": "object",
        "properties": {
            "job_id": {"type": "string"},
            "text": {"type": "string"},
            "fail": {"type": "boolean"},
            "steps": {"type": "integer", "minimum": 1, "maximum": 20},
            "delay": {"type": "number", "minimum": 0, "maximum": 2},
        },
        "required": ["job_id", "text", "fail", "steps", "delay"],
        "additionalProperties": False,
    }
    example = Plugin(
        NAMESPACE,
        (
            RegistryEntry(ASSEMBLY, "assembly", assemble, NAMESPACE),
            RegistryEntry(ADAPTER, "adapter", create_model, NAMESPACE, register_to=ADAPTERS),
            *(
                RegistryEntry(key, "state_key", StateKey(validator), NAMESPACE)
                for key, validator in (
                    (SETTINGS, validate_settings),
                    (REQUEST, validate_request),
                    (WORLD, None),
                    (STATUS, None),
                    (REPORTS, None),
                    (PIPELINE, None),
                )
            ),
            *(
                entry_from(getattr(Workshop, name), provider=NAMESPACE)
                for name in ("prepare", "start_world", "stop_world", "start_cadence", "stop_cadence")
            ),
            *(
                entry
                for key in (INSPECT, REPORT, *(Id(f"{NAMESPACE}:handlers/{name}") for name in STEPS))
                for entry in component_entries(key, declared, declared, provider=NAMESPACE)
            ),
            RegistryEntry(
                INSPECT_TOOL,
                "tool",
                ToolSpec(INSPECT, {"name": "inspect", "description": "分步巡检并计算统计", "parameters": tool_schema}),
                NAMESPACE,
                register_to=TOOLS,
            ),
            RegistryEntry(
                REPORT_TOOL,
                "tool",
                ToolSpec(
                    REPORT,
                    {
                        "name": "publish_report",
                        "description": "将巡检结果发布到报告台账",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "source": {"type": "string"},
                                "text": {"type": "string"},
                                "result": {"type": "object"},
                            },
                            "required": ["source", "text", "result"],
                            "additionalProperties": False,
                        },
                    },
                    factory=create_reporter,
                ),
                NAMESPACE,
                register_to=TOOLS,
            ),
        ),
    )
    selected = (
        adapter_plugin(),
        control_plugin(),
        model_plugin(),
        react_plugin(),
        tools_plugin(),
        defaults_plugin(),
        assembly_plugin(),
        world_plugin(),
        example,
    )
    resources = {CONFIG: "bot.toml", MODEL_CONFIG: "profiles.toml", BINDINGS: "bindings.toml"}
    return tuple(
        replace(
            item,
            entries=tuple(
                replace(
                    entry,
                    target=replace(
                        entry.target, config=ConfigTemplate(__name__, "config.tomls/" + resources[entry.id])
                    ),
                )
                if entry.id in resources and isinstance(entry.target, StateKey)
                else entry
                for entry in item.entries
            ),
        )
        for item in selected
    )
