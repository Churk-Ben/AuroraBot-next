"""验证自定义宿主直接装配 agent 运行管理，无需 bot 框架。"""

import asyncio
from contextlib import contextmanager

from aurora_agent.react import ReActAgent, plugin
from aurora_agent.runtime import AgentRuntime
from aurora_control import ExecutionPlug, ExecutionRequest, InstanceStateBinding, StateBinding, component_entries
from aurora_core.bootstrap import bootstrap
from aurora_core.ctx import Context, StateKey
from aurora_core.discovery import register_plugins
from aurora_core.hooks import HookConnections
from aurora_core.ids import Id
from aurora_core.registry import RegistryEntry


@contextmanager
def standalone(infer, *, cleanup=None):
    registry = bootstrap()
    register_plugins(registry, (plugin(),))
    state = Id("dev.standalone:state/agent")
    registry.register(RegistryEntry(state, "state_key", StateKey(), "standalone"))
    ctx, hooks = Context(registry), HookConnections(registry)
    agent = ReActAgent(
        ctx,
        hooks,
        inbox=InstanceStateBinding(state, (("part", "inbox"),)),
        progress=InstanceStateBinding(state, (("part", "progress"),)),
        runtime=InstanceStateBinding(state, (("part", "runtime"),)),
        batch=StateBinding(state, (("part", "batch"),)),
        decision=StateBinding(state, (("part", "decision"),)),
        max_iterations=5,
    )
    running = False
    received = []

    async def execute(request):
        nonlocal running
        running = True
        try:
            await agent.execute(request)
        finally:
            try:
                if cleanup is not None:
                    await cleanup()
            finally:
                running = False

    def connect(phase, handler):
        identity = Id(f"dev.standalone:handlers/{phase}")
        registry.register_many(component_entries(identity, handler, handler, provider="standalone"))
        agent.slots[phase].connect(ExecutionPlug(identity, handler))

    async def prepare(request):
        batch = agent.batch.get(ctx, request)
        assert isinstance(batch, list)
        received.extend(batch)

    async def decide(request):
        await infer()
        agent.decision.set(ctx, request, "finish")

    connect("prepare", prepare)
    connect("infer", decide)
    runtime = AgentRuntime(get_agent=lambda: agent, execute=execute, is_executing=lambda: running)
    try:
        yield agent, runtime, connect, received
    finally:
        hooks.close()
        ctx.close()


def test_standalone_runtime_guidance_finish_boundary_and_waiter_cancellation():
    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()

        async def infer():
            entered.set()
            await release.wait()

        with standalone(infer) as (_, runtime, connect, received):
            followups = []

            async def finish(request):
                if not followups:
                    followups.append(runtime.submit("收尾后的输入"))

            connect("finish", finish)
            runtime.start()
            try:
                first = runtime.submit("开始")
                await asyncio.wait_for(entered.wait(), 2)
                second = runtime.submit("运行中引导")
                assert second.run is first.run
                waiter = asyncio.create_task(first.run.wait())
                await asyncio.sleep(0)
                waiter.cancel()
                result = await asyncio.gather(waiter, return_exceptions=True)
                assert isinstance(result[0], asyncio.CancelledError)
                assert not first.run.done
                release.set()
                assert (await asyncio.wait_for(first.run.wait(), 2)).status == "completed"
                assert followups[0].run is not first.run
                assert (await asyncio.wait_for(followups[0].run.wait(), 2)).status == "completed"
                assert [item["payload"] for item in received] == ["开始", "运行中引导", "收尾后的输入"]
            finally:
                await runtime.close()

    asyncio.run(scenario())


def test_standalone_runtime_cancel_waits_for_host_cleanup():
    async def scenario():
        entered, cleaning, release = asyncio.Event(), asyncio.Event(), asyncio.Event()

        async def infer():
            entered.set()
            await asyncio.Event().wait()

        async def cleanup():
            cleaning.set()
            await release.wait()

        with standalone(infer, cleanup=cleanup) as (agent, runtime, _, received):
            runtime.start()
            try:
                first = runtime.submit("开始")
                await asyncio.wait_for(entered.wait(), 2)
                runtime.submit("等待下次显式激活")
                cancelling = asyncio.create_task(runtime.cancel(first.run.run_id))
                await asyncio.wait_for(cleaning.wait(), 2)
                assert not cancelling.done() and not first.run.done
                release.set()
                assert await asyncio.wait_for(cancelling, 2)
                assert (await first.run.wait()).status == "cancelled"
                assert [item["payload"] for item in received] == ["开始"]
                assert len(agent.pending(ExecutionRequest("pending-check"))) == 1
            finally:
                release.set()
                await runtime.close()

    asyncio.run(scenario())
