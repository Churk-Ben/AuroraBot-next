"""真实 Node 客户端与 Python API 共用 ctx 用例并验证跨宿主重连。"""

import asyncio
import json
from dataclasses import replace
from pathlib import Path

import pytest
from aurora_api.client import CtxClient, RemoteError
from aurora_api.protocol import SUBSCRIBE, UNSUBSCRIBE
from aurora_api.server import serve
from aurora_core.bootstrap import bootstrap
from aurora_core.ctx import StateKey, install_context
from aurora_core.ids import Id
from aurora_core.registry import RegistryEntry

ROOT = Path(__file__).resolve().parents[2]
PUBLIC = Id("dev.client:state/public")
PRIVATE = Id("dev.client:state/private")


def host():
    registry = bootstrap()
    registry.register_many(RegistryEntry(key, "state_key", StateKey(), "test") for key in (PUBLIC, PRIVATE))
    ctx = install_context(registry)
    active = set()
    empty = asyncio.Event()

    def subscribe(callback, **filters):
        handle = ctx.subscribe(callback, **filters)
        active.add(handle)
        empty.clear()
        return handle

    def unsubscribe(handle):
        active.remove(handle)
        if not active:
            empty.set()
        return ctx.unsubscribe(handle)

    registry.replace(replace(registry.get(SUBSCRIBE), target=subscribe))
    registry.replace(replace(registry.get(UNSUBSCRIBE), target=unsubscribe))
    return registry, ctx, active, empty


def test_python_and_typescript_share_ctx_cases_and_reconnect_after_host_restart():
    async def scenario():
        registry, ctx, active, _ = host()
        server = serve(registry, keys=[PUBLIC], port=0)
        url = await server.__aenter__()
        process = None
        try:
            cases = json.loads((ROOT / "tests/fixtures/ctx_cases.json").read_text(encoding="utf-8"))
            async with CtxClient(url) as client:
                for case in cases:
                    if "error" in case:
                        with pytest.raises(RemoteError) as error:
                            await client.request(case["action"], **case["request"])
                        assert error.value.code == case["error"]
                    else:
                        assert await client.request(case["action"], **case["request"]) == case["result"]
            for address in ctx.list():
                ctx.delete(address.key, location=dict(address.location))
            process = await asyncio.create_subprocess_exec(
                "node",
                str(ROOT / "tests/fixtures/ts_client_process.mjs"),
                url,
                cwd=ROOT,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            assert process.stdin and process.stdout and process.stderr
            checkpoint = await asyncio.wait_for(process.stdout.readline(), timeout=15)
            if not checkpoint:
                pytest.fail((await process.stderr.read()).decode("utf-8"))
            assert json.loads(checkpoint) == {"event": "restart"}
            assert len(active) == 1
            await server.__aexit__(None, None, None)
            assert not active
            ctx.close()
            registry, ctx, active, empty = host()
            ctx.set(PUBLIC, "重启后的状态")
            server = serve(registry, keys=[PUBLIC], port=int(url.rsplit(":", 1)[1]))
            assert await server.__aenter__() == url
            process.stdin.write(b"continue\n")
            await process.stdin.drain()
            output, errors = await asyncio.wait_for(process.communicate(), timeout=15)
            assert process.returncode == 0, errors.decode("utf-8")
            assert json.loads(output) == {"event": "complete", "cases": len(cases)}
            await asyncio.wait_for(empty.wait(), timeout=2)
            assert not active
            assert ctx.get(PUBLIC) == "重连后完成"
            assert len(ctx.list()) == 1
        finally:
            if process is not None and process.returncode is None:
                process.kill()
                await process.communicate()
            await server.__aexit__(None, None, None)
            ctx.close()

    asyncio.run(scenario())
