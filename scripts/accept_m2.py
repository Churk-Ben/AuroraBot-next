"""显式连接真实模型，经 CLI 验收工具往返、终态一致性及重启恢复。"""

import argparse
import asyncio
import json
import logging
import os
from io import StringIO
from pathlib import Path
from uuid import uuid4

import tomli_w
from aurora_bot.control import ExecutionPlug, component_entries
from aurora_bot.tools import TOOLS, ToolInstance, ToolSpec
from aurora_cli.commander import run_cli
from aurora_core.discovery import Plugin
from aurora_core.ids import Id
from aurora_core.registry import RegistryEntry

PLUGINS = (
    "aurora_model_adapter",
    "aurora_bot.model",
    "aurora_bot.react",
    "aurora_bot.tools",
    "aurora_bot.react_defaults",
    "aurora_bot.assembly",
)
TOOL = Id("dev.acceptance.m2:tools/echo")
HANDLER = Id("dev.acceptance.m2:handlers/echo")
BOT = "org.aurora.bot:state/"
MODEL = "org.aurora.model_adapter:state/"


async def accept(args: argparse.Namespace, *, streaming: bool) -> dict[str, object]:
    root = args.data_dir / ("stream" if streaming else "complete")
    calls: list[str] = []
    closed: list[str] = []
    nonce = uuid4().hex

    async def create_tool(*, ctx, storage, instance_id, input_state, output_state, config):
        async def execute(request):
            value = input_state.get(ctx, request)["arguments"]["text"]
            calls.append(value)
            output_state.set(ctx, request, "已核验:" + value)

        async def close():
            closed.append(instance_id)

        return ToolInstance(
            ExecutionPlug(HANDLER, execute, {"input": input_state, "output": output_state}, instance_id=instance_id),
            close,
        )

    async def placeholder(request):
        raise AssertionError("工具须经实例工厂绑定")

    fixture = Plugin(
        "m2_acceptance",
        (
            *component_entries(HANDLER, placeholder, placeholder, provider="m2_acceptance"),
            RegistryEntry(
                TOOL,
                "tool",
                ToolSpec(
                    HANDLER,
                    {
                        "name": "acceptance_echo",
                        "description": "执行本地验收回显，返回经过核验的输入标记",
                        "parameters": {
                            "type": "object",
                            "properties": {"text": {"type": "string"}},
                            "required": ["text"],
                            "additionalProperties": False,
                        },
                    },
                    factory=create_tool,
                ),
                "m2_acceptance",
                register_to=TOOLS,
            ),
        ),
    )
    base = ["--data-dir", str(root)]
    for name in PLUGINS:
        base.extend(("--plugin", name))

    async def cli(*arguments: str, assembly: bool = False) -> str:
        output = StringIO()
        selection = ["--assembly", "org.aurora.bot:assemblies/default"] if assembly else []
        status = await run_cli([*base, *selection, *arguments], plugins=(fixture,), output=output)
        if status != 0:
            raise AssertionError(f"CLI 验收失败，退出码：{status}")
        return output.getvalue()

    profile = {
        "adapter": "org.aurora.model_adapter:adapters/litellm",
        "model": args.model,
        "credential": args.credential_env,
    }
    if args.base_url is not None:
        profile["base_url"] = args.base_url
    config = {
        "instance_id": "main",
        "model_role": "reasoning",
        "streaming": streaming,
        "max_iterations": 4,
        "tools": [{"tool": str(TOOL), "instance_id": "echo", "config": {}}],
    }
    for key, value in (
        (BOT + "config", config),
        (MODEL + "config", {"primary": profile}),
        (MODEL + "bindings", {"reasoning": "primary"}),
    ):
        relative = {
            BOT + "config": "org.aurora.bot/config.toml",
            MODEL + "config": "org.aurora.model_adapter/profiles.toml",
            MODEL + "bindings": "org.aurora.model_adapter/bindings.toml",
        }[key]
        path = root / "config" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(tomli_w.dumps(value), encoding="utf-8")

    output = await cli(
        "org.aurora.bot:commands/run/submit",
        f"请调用 acceptance_echo 工具一次，text 参数必须为 {nonce}。收到工具结果后，只输出工具返回的文本，不再调用工具。",
        "--instance-id",
        "main",
        assembly=True,
    )
    records = [json.loads(line) for line in output.splitlines()]
    receipt, result = records[0], records[-1]
    assert result["event"] == "result" and result["status"] == "completed"
    assert {record["run_id"] for record in records} == {receipt["run_id"]}
    terminal = [
        record["state"] for record in records if record["event"] == "run" and record["state"]["status"] != "running"
    ]
    assert len(terminal) == 1 and terminal[0]["status"] == result["status"]
    assert calls == [nonce] and len(closed) == 1
    assert len({record["execution_id"] for record in records if record["event"] == "model"}) == 2

    snapshot = json.loads((root / "framework" / "ctx.json").read_text(encoding="utf-8"))
    entries = {
        entry["id"]: entry["value"] for entry in snapshot["entries"] if entry["location"] == {"instance_id": "main"}
    }
    assert entries[BOT + "run"] == terminal[0]
    context = entries[BOT + "messages"]
    observations = [json.loads(message["content"]) for message in context["messages"] if message["role"] == "tool"]
    assert len(observations) == 1 and observations[0]["status"] == "completed"
    assert observations[0]["value"] == "已核验:" + nonce
    assert context["pending"] is None and "已核验:" + nonce in context["messages"][-1]["content"]
    restored = json.loads(
        await cli("ctx", "get", BOT + "messages", "--location", '{"instance_id":"main"}', assembly=True)
    )
    assert restored == context and calls == [nonce] and len(closed) == 2
    assert json.loads(await cli("ctx", "get", BOT + "config")) == config
    assert json.loads(await cli("ctx", "get", MODEL + "bindings")) == {"reasoning": "primary"}

    secret = os.environ[args.credential_env]
    assert secret not in output
    for path in root.rglob("*"):
        if path.is_file() and path.suffix in {".json", ".log"}:
            assert secret not in path.read_text(encoding="utf-8"), f"验收产物包含凭证：{path}"
    (root / "events.jsonl").write_text(output, encoding="utf-8")
    return {
        "streaming": streaming,
        "run_id": result["run_id"],
        "status": result["status"],
        "tool_calls": len(calls),
        "nonempty_deltas": sum(bool(record["delta"]) for record in records if record["event"] == "model"),
        "restored": True,
        "credential_absent": True,
    }


async def run(args: argparse.Namespace) -> None:
    if not os.environ.get(args.credential_env):
        raise ValueError(f"缺少环境凭证：{args.credential_env}")
    args.data_dir.mkdir(parents=True, exist_ok=False)
    # 验收输出聚焦 CLI 记录；SDK 调试日志可包含完整请求与响应。
    for name in ("LiteLLM", "LiteLLM Router", "LiteLLM Proxy"):
        logging.getLogger(name).setLevel(logging.WARNING)
    results = []
    for streaming in (True, False):
        async with asyncio.timeout(args.timeout):
            result = await accept(args, streaming=streaming)
        results.append(result)
        print(json.dumps(result, ensure_ascii=False), flush=True)
    (args.data_dir / "report.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="真实模型的 M2 CLI 工具往返验收，会调用所选供应商")
    parser.add_argument("--data-dir", type=Path, required=True, help="必须为尚不存在的独立验收目录")
    parser.add_argument("--model", default="deepseek/deepseek-flash")
    parser.add_argument("--credential-env", default="DEEPSEEK_API_KEY")
    parser.add_argument("--base-url")
    parser.add_argument("--timeout", type=float, default=90, help="每种模式的总时限（秒）")
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
