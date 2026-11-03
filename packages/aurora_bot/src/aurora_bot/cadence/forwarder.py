"""订阅世界记录并向默认 bot 的既有运行所有者逐条提交。"""

import asyncio
import logging
from dataclasses import asdict
from typing import cast

from aurora_agent.react import AgentBusyError
from aurora_agent.runtime import AgentRuntime
from aurora_core import entry_from, hook_handler
from aurora_core.ctx import Context, StateChange
from aurora_core.hooks import HookConnections
from aurora_core.lifecycle import PREPARE, START, STOP, LifecycleComponent
from aurora_model_adapter import JsonValue
from aurora_world import RECORDS, CursorError, WorldRecords

from ..assembly_config import CONFIG as BOT_CONFIG
from .state import CADENCE_CONFIG, CHECKPOINT, CONFIG_STATE, position

logger = logging.getLogger(__name__)


class Cadence:
    """每个默认 bot 仅装配一个转发所有者；不创建激活或等待业务完成。

    持久状态按 bot instance_id 定位。首次启用从当前保留窗口开始，之后严格遵循游标；
    来源选择变化、裁剪缺口和未知转交均暂停，重启不能自动清除诊断。完整回执保留原始
    消息和引导关联，适用于有限规模输入，不承诺逐条落盘或崩溃下的恰好一次执行。
    """

    def __init__(self, ctx: Context, hooks: HookConnections, runtime: AgentRuntime, *, instance_id: str) -> None:
        self.ctx, self.hooks, self.runtime = ctx, hooks, runtime
        self.instance_id = instance_id
        self._location: dict[str, str] = {}
        self._state: dict = {}
        self._accepting = False
        self._subscription: str | None = None
        self._worker: asyncio.Task[None] | None = None
        self._changed = asyncio.Event()

    def component(self, *, depends_on: tuple[str, ...]) -> LifecycleComponent:
        links = []
        try:
            for phase, method in ((PREPARE, self.prepare), (START, self.start), (STOP, self.stop)):
                definition = entry_from(method, provider="aurora_bot.cadence")
                links.append(
                    self.hooks.connect(
                        phase,
                        definition.id,
                        slot_instance=self.instance_id,
                        handler_instance=self.instance_id,
                        target=method,
                    )
                )
        except Exception:
            for link in links:
                self.hooks.disconnect(link)
            raise
        return LifecycleComponent(self.instance_id, depends_on=depends_on, stop_accepting=self.stop_accepting)

    def _save(self, **changes: object) -> None:
        state = {**self._state, **changes}
        self.ctx.set(CHECKPOINT, state, location=self._location)
        self._state = state

    def _pause(self, error: str) -> None:
        self.stop_accepting()
        self._save(error=error)
        logger.error("cadence 已暂停：%s", error)

    @hook_handler("org.aurora.bot:handlers/cadence/prepare", slot=PREPARE)
    def prepare(self) -> None:
        selected = cast(dict, CADENCE_CONFIG.parse(self.ctx.get(CONFIG_STATE)))["source_ids"]
        self._location = {"instance_id": cast(dict, self.ctx.get(BOT_CONFIG))["instance_id"]}
        try:
            self._state = cast(dict, self.ctx.get(CHECKPOINT, location=self._location))
        except KeyError:
            self._state = {
                "version": 1,
                "source_ids": sorted(selected),
                "position": None,
                "pending": None,
                "receipts": [],
                "error": None,
            }
            if selected:
                self._save()
        if self._state["pending"] is not None:
            self._pause("TransferUncertain")
        elif self._state["source_ids"] != sorted(selected):
            self._pause("SelectionChanged")

    @hook_handler("org.aurora.bot:handlers/cadence/start", slot=START)
    def start(self) -> None:
        if self._state["error"] is not None or not self._state["source_ids"]:
            return
        self._accepting = True
        self._subscription = self.ctx.subscribe(self._notify, key=RECORDS, location={})
        self._changed.set()
        self._worker = asyncio.create_task(self._forward(), name=f"cadence-{self.instance_id}")

    def _notify(self, change: StateChange) -> None:
        self._changed.set()

    async def _forward(self) -> None:
        records = WorldRecords(self.ctx)
        try:
            while self._accepting:
                await self._changed.wait()
                self._changed.clear()
                while self._accepting:
                    batch = records.read(after=position(self._state["position"]), limit=1)
                    if not batch:
                        break
                    record = batch[0]
                    anchor = asdict(record.position)
                    if record.source_id not in self._state["source_ids"]:
                        self._save(position=anchor)
                    else:
                        message = {
                            "position": anchor,
                            "source_id": record.source_id,
                            "message_id": record.message_id,
                            "payload": record.payload,
                        }
                        self._save(pending=message)
                        try:
                            receipt = self.runtime.submit(cast(JsonValue, record.payload))
                        except AgentBusyError:
                            # Runtime 在写入前拒绝取消期间的提交，等待同一运行收尾后重新读取。
                            self._save(pending=None)
                            current = self.runtime.current
                            if current is None:
                                self._pause("RuntimeBusy")
                                return
                            await current.wait()
                            await asyncio.sleep(0)
                            continue
                        except Exception:  # noqa: BLE001 - 提交可能已写入 inbox，禁止自动重放。
                            self._pause("TransferUncertain")
                            return
                        self._save(
                            position=anchor,
                            pending=None,
                            receipts=[
                                *self._state["receipts"],
                                {
                                    "message": message,
                                    "guidance_id": receipt.guidance_id,
                                    "sequence": receipt.sequence,
                                    "run_id": receipt.run.run_id,
                                },
                            ],
                        )
                    await asyncio.sleep(0)
        except asyncio.CancelledError:
            return
        except CursorError:
            self._pause("CursorInvalid")
        except Exception:  # noqa: BLE001 - 保留 pending 与游标，状态写入失败继续向宿主报告。
            self._pause("TransferUncertain" if self._state.get("pending") is not None else "ForwarderFailed")

    def stop_accepting(self) -> None:
        self._accepting = False
        if self._subscription is not None:
            self.ctx.unsubscribe(self._subscription)
            self._subscription = None
        if (
            self._worker is not None
            and self._worker is not asyncio.current_task()
            and not self._worker.done()
            and not self._worker.cancelling()
        ):
            self._worker.cancel()

    @hook_handler("org.aurora.bot:handlers/cadence/stop", slot=STOP)
    async def stop(self) -> None:
        self.stop_accepting()
        if self._worker is not None:
            try:
                await asyncio.shield(self._worker)
            except asyncio.CancelledError:
                if not self._worker.cancelled():
                    raise
