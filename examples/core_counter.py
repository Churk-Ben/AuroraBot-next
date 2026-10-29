"""仅依赖 aurora_core 的持久化计数器应用。"""

import argparse
import asyncio
from pathlib import Path

from aurora_core import Id, entry_from, hook_handler, operation
from aurora_core.bootstrap import bootstrap
from aurora_core.ctx import Context, StateKey, install_context
from aurora_core.discovery import Plugin, load_plugins, register_plugins
from aurora_core.hooks import HookConnections, HookSlot
from aurora_core.invocation import invoke_operation
from aurora_core.persistence import ContextPersistence
from aurora_core.registry import RegistryEntry
from aurora_core.storage import StorageService

COUNT = Id("dev.example.counter:state/count")
INCREMENT = Id("dev.example.counter:slots/increment")
ADD = Id("dev.example.counter:operations/add")
PROVIDER = "core_counter"


def validate_count(value: object) -> None:
    if type(value) is not int:
        raise TypeError("计数值必须为整数")


class Counter:
    def __init__(self, ctx: Context, name: str) -> None:
        self.ctx = ctx
        self.location = {"counter": name}

    @hook_handler("dev.example.counter:handlers/increment", slot=INCREMENT)
    def increment(self, amount: int) -> int:
        try:
            previous = self.ctx.get(COUNT, location=self.location)
        except KeyError:
            previous = 0
        if type(previous) is not int:
            raise TypeError("计数值必须为整数")
        current = previous + amount
        self.ctx.set(COUNT, current, location=self.location)
        return current


async def run_counter(data_dir: Path, name: str, amount: int) -> int:
    if not name:
        raise ValueError("计数器名称不能为空")
    registry = bootstrap()
    plugin = Plugin(
        PROVIDER,
        (
            RegistryEntry(
                COUNT,
                "state_key",
                StateKey(validate_count),
                PROVIDER,
                register_to=Id("org.aurora.core:registries/state_keys"),
            ),
            RegistryEntry(
                INCREMENT, "hook_slot", HookSlot(), PROVIDER, register_to=Id("org.aurora.core:registries/hook_slots")
            ),
            entry_from(Counter.increment, provider=PROVIDER),
        ),
    )
    register_plugins(registry, load_plugins(explicit=(plugin,)))
    ctx = install_context(registry)
    storage = StorageService(data_dir)
    hooks = HookConnections(registry)
    try:
        persistence = ContextPersistence(ctx, storage.snapshot_store())
        await persistence.start()
    except BaseException:
        hooks.close()
        storage.close()
        ctx.close()
        raise
    try:
        counter = Counter(ctx, name)
        binding = hooks.connect(
            INCREMENT,
            Id("dev.example.counter:handlers/increment"),
            slot_instance="application",
            handler_instance=name,
            target=counter.increment,
        )

        @operation(ADD)
        async def add(value: int) -> object:
            return await hooks.invoke(binding, value)

        registry.register(entry_from(add, provider=PROVIDER))
        ctx.subscribe(lambda change: print(f"{name}: {change.value}"), key=COUNT, location={"counter": name})
        result = await invoke_operation(registry, ADD, amount)
        if type(result) is not int:
            raise TypeError("计数操作必须返回整数")
        return result
    finally:
        hooks.close()
        await persistence.close()
        storage.close()
        ctx.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="通过 core 声明、连接与持久化运行计数器")
    parser.add_argument("--data-dir", type=Path, required=True, help="持久化数据目录")
    parser.add_argument("--name", default="default", help="计数器名称")
    parser.add_argument("--amount", type=int, default=1, help="本次增量，可为负数")
    args = parser.parse_args()
    asyncio.run(run_counter(args.data_dir, args.name, args.amount))


if __name__ == "__main__":
    main()
