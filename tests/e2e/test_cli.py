"""验证 CLI 状态命令、第三方声明和装配生命周期。"""

import asyncio
import json
import subprocess
import sys
import tomllib
from importlib.metadata import version
from io import StringIO

import pytest
from aurora_cli.commander import run_cli
from aurora_core import Id, entry_from, hook_handler, operation
from aurora_core.discovery import Plugin
from aurora_core.lifecycle import PREPARE, START, STOP, LifecycleComponent
from aurora_core.registry import RegistryEntry

CONFIG = "org.aurora.cli:state/config"


@pytest.mark.parametrize("flag", ["-v", "--version"])
def test_version_exits_without_loading_plugins_or_creating_storage(tmp_path, flag):
    result = invoke("--plugin", "missing-version-test-plugin", "--data-dir", tmp_path / "data", flag)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == f"aurora {version('aurora-cli')}"
    assert not (tmp_path / "data").exists()


def invoke(*args):
    return subprocess.run(
        [sys.executable, "-m", "aurora_cli", *map(str, args)], check=False, capture_output=True, text=True, timeout=15
    )


def test_ctx_commands_recover_across_processes(tmp_path):
    def run(*args):
        result = invoke("--data-dir", tmp_path, *args)
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)

    assert run("ctx", "set", CONFIG, '{"value":1}') is None
    assert run("ctx/get", CONFIG) == {"value": 1}
    assert run("ctx", "set", CONFIG, '{"value":2}', "--location", '{"scope":"other"}') is None
    assert run("ctx/list", "--location", "{}") == [{"id": CONFIG, "location": {}}]
    assert run("ctx", "get", CONFIG, "--location", '{"scope":"other"}') == {"value": 2}
    assert run("ctx/delete", CONFIG) is True
    assert run("ctx/delete", CONFIG) is False
    missing = invoke("--data-dir", tmp_path, "ctx/get", CONFIG)
    assert missing.returncode == 1
    assert "KeyError" in missing.stderr


def test_help_and_bad_arguments_do_not_create_storage(tmp_path):
    for args in (["--help"], ["help"], ["ctx"], ["ctx", "--help"], ["ctx", "get", "--help"]):
        result = invoke("--data-dir", tmp_path / "unused", *args)
        assert result.returncode == 0
        assert result.stdout
    for args in (
        ["ctx/set", CONFIG, "NaN"],
        ["ctx/get", CONFIG, "--location", '{"scope":1}'],
        ["--config", "[]", "ctx/list"],
    ):
        result = invoke("--data-dir", tmp_path / "unused", *args)
        assert result.returncode == 2
    assert not (tmp_path / "unused").exists()


def test_project_commands_and_groups_do_not_require_host_storage(tmp_path):
    for args in (["about"], ["donk"], ["donk", "--help"], ["check", "--help"]):
        result = invoke("--root", tmp_path, *args)
        assert result.returncode == 0, result.stderr
        assert "\x1b" not in result.stdout
        assert result.stdout
    assert list(tmp_path.iterdir()) == []
    assert invoke("check", "--li").returncode == 2
    assert invoke("--roo", tmp_path, "about").returncode == 2


def test_donk_updates_versions_and_real_uv_lock(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "aurorabot-ai"\nversion = "0.1.0"\nrequires-python = ">=3.12"\n'
        'dependencies = ["aurora-core>=0.1.0"]\n'
        '[tool.uv.workspace]\nmembers = ["core"]\n'
        "[tool.uv.sources]\naurora-core = { workspace = true }\n",
        encoding="utf-8",
    )
    (tmp_path / "core").mkdir()
    (tmp_path / "core" / "pyproject.toml").write_text(
        '[project]\nname = "aurora-core"\nversion = "0.1.0"\nrequires-python = ">=3.12"\n',
        encoding="utf-8",
    )
    result = invoke("--root", tmp_path, "donk", "patch")
    assert result.returncode == 0, result.stderr
    lock = tomllib.loads((tmp_path / "uv.lock").read_text(encoding="utf-8"))
    assert {package["name"]: package["version"] for package in lock["package"]} == {
        "aurorabot-ai": "0.1.1",
        "aurora-core": "0.1.1",
    }
    root = tomllib.loads((tmp_path / "pyproject.toml").read_text(encoding="utf-8"))
    assert root["project"]["dependencies"] == ["aurora-core>=0.1.1"]


def test_extension_command_uses_operation_without_cli_types(tmp_path):
    @operation("dev.test:operations/add")
    async def add(value: int, amount: int = 1):
        return value + amount

    plugin = Plugin(
        "test",
        (
            entry_from(add, provider="test"),
            RegistryEntry(
                Id("dev.test:commands/add"),
                "command",
                {
                    "help": "增加数值",
                    "operation": "dev.test:operations/add",
                    "arguments": [
                        {"name": "value", "type": "integer"},
                        {"name": "amount", "type": "integer", "option": True},
                    ],
                },
                "test",
                register_to=Id("org.aurora.cli:registries/commands"),
            ),
        ),
    )
    output = StringIO()
    asyncio.run(
        run_cli(
            ["--data-dir", str(tmp_path), "--namespace", "dev.test", "add", "2", "--amount", "3"],
            plugins=[plugin],
            output=output,
        )
    )
    assert json.loads(output.getvalue()) == 5


def test_run_applies_config_before_prepare_and_flushes_stop(tmp_path):
    async def scenario():
        started = asyncio.Event()
        observations = []

        def factory(*, registry, ctx, hooks, storage):
            @hook_handler("dev.test:handlers/prepare", slot=PREPARE)
            def prepare():
                observations.append(ctx.get(Id(CONFIG)))

            @hook_handler("dev.test:handlers/start", slot=START)
            def start():
                started.set()

            @hook_handler("dev.test:handlers/stop", slot=STOP)
            def stop():
                ctx.set(Id(CONFIG), {"stopped": True})
                storage.set("dev.test", "finished", True)

            for phase, callback in ((PREPARE, prepare), (START, start), (STOP, stop)):
                entry = entry_from(callback, provider="test")
                registry.register(entry)
                hooks.connect(phase, entry.id, slot_instance="app", handler_instance="app")
            return [LifecycleComponent("app")]

        plugin = Plugin("test", (RegistryEntry(Id("dev.test:assemblies/app"), "assembly", factory, "test"),))
        await run_cli(["--data-dir", str(tmp_path), "ctx/set", CONFIG, '{"old":true}'], output=StringIO())
        task = asyncio.create_task(
            run_cli(
                ["--data-dir", str(tmp_path), "--config", '{"new":true}', "run", "dev.test:assemblies/app"],
                plugins=[plugin],
            )
        )
        await asyncio.wait_for(started.wait(), timeout=2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert observations == [{"new": True}]
        output = StringIO()
        await run_cli(["--data-dir", str(tmp_path), "ctx/get", CONFIG], output=output)
        assert json.loads(output.getvalue()) == {"stopped": True}

    asyncio.run(scenario())
