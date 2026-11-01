"""默认 bot 装配的运行适配；调度和运行回执由 aurora_agent 提供。"""

from typing import TYPE_CHECKING

from aurora_agent.react import ReActAgent
from aurora_agent.runtime import AgentRuntime, RunHandle, RunResult, Submission

if TYPE_CHECKING:
    from .assembly import DefaultAssembly


class BotRuntime(AgentRuntime):
    """将默认装配的激活、占用和延迟创建的 agent 接入通用运行管理。"""

    def __init__(self, assembly: "DefaultAssembly") -> None:
        def get_agent() -> ReActAgent:
            if assembly.agent is None:
                raise RuntimeError("默认 bot 尚未完成装配")
            return assembly.agent

        super().__init__(
            get_agent=get_agent,
            execute=assembly._activate,
            is_executing=lambda: assembly._executing,
        )


__all__ = ["BotRuntime", "RunHandle", "RunResult", "Submission"]
