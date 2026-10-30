"""控制组件通过 ctx 协作，验证握手、选择、迭代及并发收尾。"""

import asyncio

import pytest
from aurora_bot.control import (
    CONTROL_STATE,
    Branch,
    ExecutionPlug,
    ExecutionRequest,
    ExecutionSlot,
    LoopLimitExceeded,
    Parallel,
    Serial,
    StateBinding,
    While,
    plugin,
)
from aurora_core.bootstrap import bootstrap
from aurora_core.ctx import Context, StateKey
from aurora_core.discovery import register_plugins
from aurora_core.hooks import HookConnections
from aurora_core.ids import Id
from aurora_core.registry import RegistryEntry

DATA = Id("dev.example:state/component")


@pytest.fixture
def runtime():
    registry = bootstrap()
    register_plugins(registry, (plugin(),))
    registry.register(RegistryEntry(DATA, "state_key", StateKey(), "example"))
    ctx = Context(registry)
    hooks = HookConnections(registry)
    yield registry, ctx, hooks
    hooks.close()
    ctx.close()


def binding(instance):
    return StateBinding(DATA, (("instance_id", instance),))


def status(ctx, instance, request):
    return ctx.get(
        CONTROL_STATE,
        location={"instance_id": instance, "run_id": request.run_id, "execution_id": request.execution_id},
    )


def capture_terminals(ctx):
    """测试订阅者按需收集终态，控制组件自身不保存历史。"""
    records = {}

    def observe(change):
        if change.action == "set" and change.value["status"] != "running":
            location = dict(change.address.location)
            records[(location["instance_id"], location["execution_id"])] = change.value

    ctx.subscribe(observe, key=CONTROL_STATE)
    return records


def test_handshake_exchanges_addresses_without_executing_and_accepts_compatible_schema(runtime, caplog):
    _, ctx, hooks = runtime
    source, output = binding("source"), binding("output")
    request = ExecutionRequest("first")
    called = []

    async def consume(execution):
        called.append(execution)
        # 消费方使用握手提供的位置读取数据，只更新自身输出。
        value = link.slot_states["input"].get(ctx, execution)
        output.set(ctx, execution, value)

    def accept(plug):
        assert isinstance(plug.schema, dict)
        return None if plug.schema["format"] == "text" else "只接收文本"

    slot = ExecutionSlot(
        "root",
        hooks,
        states={"input": source},
        schema={"format": "text"},
        accept=accept,
    )
    plug = ExecutionPlug("consumer", consume, {"output": output}, {"format": "text", "extra": True})
    link = slot.connect(plug)
    assert not called and ctx.list() == ()
    assert "兼容" in caplog.text
    assert link.plug.states["output"] == output
    assert link.slot_schema == {"format": "text"}
    with pytest.raises(ValueError, match="只接收文本"):
        slot.connect(ExecutionPlug("rejected", consume, schema={"format": "binary"}))
    source.set(ctx, request, "内容仅存于 ctx")
    assert asyncio.run(slot.invoke(link, request)) is None
    assert output.get(ctx, request) == "内容仅存于 ctx"
    assert called == [request]


def test_serial_order_waits_and_does_not_forward_results(runtime):
    _, ctx, hooks = runtime
    slot = ExecutionSlot("root", hooks)
    source, result = binding("source"), binding("result")
    requests = []

    async def produce(request):
        await asyncio.sleep(0)
        source.set(ctx, request, 7)
        requests.append(request)

    async def consume(request):
        result.set(ctx, request, source.get(ctx, request))
        requests.append(request)

    slot.connect(ExecutionPlug("consume", consume), priority=2)
    slot.connect(ExecutionPlug("produce", produce, {"output": source}), priority=1)
    controller = Serial(ctx, slot)
    request = ExecutionRequest("run")
    changes = []
    ctx.subscribe(changes.append, key=CONTROL_STATE)
    assert asyncio.run(controller.execute(request)) is None
    assert result.get(ctx, request) == 7
    assert len({item.execution_id for item in requests}) == 2
    assert all(item.parent_execution_id == request.execution_id for item in requests)
    assert ctx.list(key=CONTROL_STATE) == ()
    assert [change.value["status"] for change in changes if change.action == "set"] == ["running", "completed"]
    assert changes[-1].action == "delete"


def test_serial_failure_does_not_start_next_child(runtime):
    _, ctx, hooks = runtime
    terminals = capture_terminals(ctx)
    slot = ExecutionSlot("root", hooks)
    called = []

    async def fail(request):
        raise ValueError("业务失败")

    async def later(request):
        called.append(request)

    slot.connect(ExecutionPlug("fail", fail))
    slot.connect(ExecutionPlug("later", later))
    request = ExecutionRequest("run")
    with pytest.raises(ValueError, match="业务失败"):
        asyncio.run(Serial(ctx, slot).execute(request))
    assert not called
    assert terminals[("root", request.execution_id)]["status"] == "failed"
    assert ctx.list(key=CONTROL_STATE) == ()


@pytest.mark.parametrize("selected", ["left", "right", None, "missing"])
def test_branch_uses_ctx_selection(runtime, selected):
    _, ctx, hooks = runtime
    slot = ExecutionSlot("branch", hooks)
    selection = binding("selection")
    called = []

    async def left(request):
        called.append("left")

    async def right(request):
        called.append("right")

    slot.connect(ExecutionPlug("left", left))
    slot.connect(ExecutionPlug("right", right))

    def select(request):
        value = selection.get(ctx, request)
        assert value is None or isinstance(value, str)
        return value

    controller = Branch(ctx, slot, select)
    request = ExecutionRequest("run")
    selection.set(ctx, request, selected)
    if selected == "missing":
        with pytest.raises(ValueError, match="分支未连接"):
            asyncio.run(controller.execute(request))
        assert not called
    else:
        asyncio.run(controller.execute(request))
        assert called == ([] if selected is None else [selected])


def test_nested_loop_reads_updated_ctx_and_assigns_fresh_invocations(runtime):
    _, ctx, hooks = runtime
    terminals = capture_terminals(ctx)
    count = binding("increment")
    calls = []

    async def increment(request):
        calls.append(request)
        value = count.get(ctx, request)
        assert isinstance(value, int)
        count.set(ctx, request, value + 1)

    def condition(request):
        value = count.get(ctx, request)
        assert isinstance(value, int)
        return value < 3

    serial_slot = ExecutionSlot("body", hooks)
    serial_slot.connect(ExecutionPlug("increment", increment, {"count": count}))
    loop_slot = ExecutionSlot("loop", hooks)
    loop_slot.connect(Serial(ctx, serial_slot).plug)
    loop = While(ctx, loop_slot, condition, max_iterations=3)
    first, second = ExecutionRequest("first"), ExecutionRequest("second")
    count.set(ctx, first, 0)
    count.set(ctx, second, 3)
    asyncio.run(loop.execute(first))
    asyncio.run(loop.execute(second))
    assert count.get(ctx, first) == count.get(ctx, second) == 3
    assert len({request.execution_id for request in calls}) == 3
    assert terminals[("loop", first.execution_id)]["iterations"] == 3
    assert terminals[("loop", second.execution_id)]["iterations"] == 0
    assert ctx.list(key=CONTROL_STATE) == ()


def test_loop_limit_fails_and_immediate_body_can_be_cancelled(runtime):
    _, ctx, hooks = runtime
    terminals = capture_terminals(ctx)
    slot = ExecutionSlot("loop", hooks)
    calls = []

    async def step(request):
        calls.append(request)

    slot.connect(ExecutionPlug("step", step))
    loop = While(ctx, slot, lambda request: True, max_iterations=2)
    request = ExecutionRequest("limit")
    with pytest.raises(LoopLimitExceeded):
        asyncio.run(loop.execute(request))
    assert len(calls) == 2
    assert terminals[("loop", request.execution_id)]["status"] == "failed"
    assert ctx.list(key=CONTROL_STATE) == ()

    async def cancel():
        request = ExecutionRequest("cancel")
        task = asyncio.create_task(While(ctx, slot, lambda request: True, max_iterations=10000).execute(request))
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert terminals[("loop", request.execution_id)]["status"] == "cancelled"
        assert ctx.list(key=CONTROL_STATE) == ()

    asyncio.run(cancel())


def test_parallel_bounds_concurrency_and_keeps_results_in_ctx(runtime):
    _, ctx, hooks = runtime

    async def scenario():
        slot = ExecutionSlot("parallel", hooks)
        release = asyncio.Event()
        two_started = asyncio.Event()
        active = 0
        peak = 0

        def worker(name):
            async def execute(request):
                nonlocal active, peak
                active += 1
                peak = max(peak, active)
                if active == 2:
                    two_started.set()
                try:
                    await release.wait()
                    binding(name).set(ctx, request, name)
                finally:
                    active -= 1

            return ExecutionPlug(name, execute)

        for name in ("a", "b", "c"):
            slot.connect(worker(name))
        request = ExecutionRequest("run")
        task = asyncio.create_task(Parallel(ctx, slot, concurrency=2).execute(request))
        await asyncio.wait_for(two_started.wait(), 1)
        assert not task.done() and active == 2
        release.set()
        assert await task is None
        assert peak == 2 and active == 0
        assert [binding(name).get(ctx, request) for name in ("a", "b", "c")] == ["a", "b", "c"]

    asyncio.run(scenario())


@pytest.mark.parametrize("outcome", ["failure", "parent_cancel", "child_cancel"])
def test_parallel_waits_for_sibling_cleanup_before_terminal_state(runtime, outcome):
    _, ctx, hooks = runtime
    terminals = capture_terminals(ctx)

    async def scenario():
        entered = asyncio.Event()
        cleaned = []
        request = ExecutionRequest("run")

        async def sibling(execution):
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                await asyncio.sleep(0)
                assert status(ctx, "parallel", request)["status"] == "running"
                cleaned.append(True)

        async def trigger(execution):
            await entered.wait()
            if outcome == "failure":
                raise ValueError("子任务失败")
            if outcome == "child_cancel":
                raise asyncio.CancelledError
            await asyncio.Event().wait()

        slot = ExecutionSlot("parallel", hooks)
        slot.connect(ExecutionPlug("sibling", sibling))
        slot.connect(ExecutionPlug("trigger", trigger))
        task = asyncio.create_task(Parallel(ctx, slot, concurrency=2).execute(request))
        await asyncio.wait_for(entered.wait(), 1)
        if outcome == "parent_cancel":
            task.cancel()
        with pytest.raises(ValueError if outcome == "failure" else asyncio.CancelledError):
            await asyncio.wait_for(task, 1)
        assert cleaned == [True]
        assert terminals[("parallel", request.execution_id)]["status"] == (
            "failed" if outcome == "failure" else "cancelled"
        )
        assert ctx.list(key=CONTROL_STATE) == ()
        assert not [item for item in asyncio.all_tasks() if item is not asyncio.current_task()]

    asyncio.run(scenario())


def test_disconnected_child_is_not_executed(runtime):
    _, ctx, hooks = runtime
    slot = ExecutionSlot("root", hooks)

    async def removed(request):
        pytest.fail("断开后不应执行")

    link = slot.connect(ExecutionPlug("removed", removed))
    hooks.disconnect(link.connection)
    asyncio.run(Serial(ctx, slot).execute(ExecutionRequest("run")))


@pytest.mark.parametrize("limit", [0, -1, 1.5, True])
def test_control_limits_require_positive_integers(runtime, limit):
    _, ctx, hooks = runtime
    slot = ExecutionSlot("root", hooks)
    with pytest.raises(ValueError, match="正整数"):
        While(ctx, slot, lambda request: True, max_iterations=limit)
    with pytest.raises(ValueError, match="正整数"):
        Parallel(ctx, slot, concurrency=limit)


def test_loop_keeps_only_active_control_state(runtime):
    _, ctx, hooks = runtime
    calls = 0
    peak = 0

    async def step(request):
        nonlocal calls, peak
        calls += 1
        addresses = ctx.list(key=CONTROL_STATE)
        peak = max(peak, len(addresses))
        for address in addresses:
            assert "children" not in ctx.get(address.key, location=dict(address.location))

    body_slot = ExecutionSlot("body", hooks)
    body_slot.connect(ExecutionPlug("step", step))
    loop_slot = ExecutionSlot("loop", hooks)
    loop_slot.connect(Serial(ctx, body_slot).plug)
    loop = While(ctx, loop_slot, lambda request: calls < 100, max_iterations=100)
    asyncio.run(loop.execute(ExecutionRequest("run")))
    assert calls == 100 and peak == 2
    assert ctx.list(key=CONTROL_STATE) == ()


def test_finishing_one_call_does_not_remove_other_active_call(runtime):
    _, ctx, hooks = runtime

    async def scenario():
        entered = {name: asyncio.Event() for name in ("first", "second")}
        release = {name: asyncio.Event() for name in entered}

        async def wait(request):
            entered[request.run_id].set()
            await release[request.run_id].wait()

        slot = ExecutionSlot("root", hooks)
        slot.connect(ExecutionPlug("wait", wait))
        root = Serial(ctx, slot)
        first, second = ExecutionRequest("first"), ExecutionRequest("second")
        first_task = asyncio.create_task(root.execute(first))
        second_task = asyncio.create_task(root.execute(second))
        await asyncio.wait_for(asyncio.gather(*(event.wait() for event in entered.values())), 1)
        assert len(ctx.list(key=CONTROL_STATE)) == 2
        release["first"].set()
        await first_task
        assert len(ctx.list(key=CONTROL_STATE)) == 1
        assert status(ctx, "root", second)["status"] == "running"
        release["second"].set()
        await second_task
        assert ctx.list(key=CONTROL_STATE) == ()

    asyncio.run(scenario())
