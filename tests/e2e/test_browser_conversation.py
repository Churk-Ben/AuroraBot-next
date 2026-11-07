"""浏览器来源的认证覆盖默认装配、直接交流和显式取消。"""

import asyncio

from aiohttp import ClientSession
from aurora_api.access import AccessPolicy
from aurora_api.server import serve
from aurora_bot.conversation import CONVERSATION
from aurora_config import CONFIGURATION
from test_default_assembly import seed, setup


def test_authenticated_browser_conversation_and_configuration(tmp_path):
    async def scenario():
        host, assembly, ctx, registry, _, _, events, entered = setup(tmp_path, behavior="wait")
        await host.start(configure=lambda: seed(ctx))
        token = "test-browser-product-token-1234567890"
        origin = "http://localhost:5173"
        access = AccessPolicy(token=token, allowed_origins=(origin,))
        try:
            async with (
                serve(registry, keys=[], endpoints=[CONVERSATION, CONFIGURATION], port=0, access=access) as url,
                ClientSession() as client,
            ):
                headers = {"Origin": origin, "Authorization": f"Bearer {token}"}

                async def call(path, body, *, authenticated=True, status=200):
                    async with client.post(
                        url + path, json=body, headers=headers if authenticated else {"Origin": origin}
                    ) as response:
                        assert response.status == status
                        assert response.headers["Access-Control-Allow-Origin"] == origin
                        return await response.json()

                for path in (
                    "/conversation/info",
                    "/conversation/submit",
                    "/conversation/cancel",
                    "/configuration/list",
                    "/configuration/save",
                ):
                    await call(path, {}, authenticated=False, status=401)
                    async with client.options(
                        url + path,
                        headers={
                            "Origin": origin,
                            "Access-Control-Request-Method": "POST",
                            "Access-Control-Request-Headers": "authorization,content-type",
                        },
                    ) as response:
                        assert response.status == 204
                assert assembly.runtime.current is None
                assert (await call("/configuration/list", {}))["result"]
                info = (await call("/conversation/info", {}))["result"]
                scope = {"session_id": info["session_id"], "instance_id": "main"}
                message = {**scope, "request_id": "browser-one", "text": "开始"}
                receipt = (await call("/conversation/submit", message))["result"]
                assert (await call("/conversation/submit", message))["result"] == receipt
                await asyncio.wait_for(entered.wait(), 2)
                assert events.count("tool.executed") == 1
                result = await call("/conversation/cancel", {**scope, "run_id": receipt["run_id"]})
                assert result["result"]["cancelled"] is True
                assert (await call("/conversation/query", {**scope, "request_id": "browser-one"}))["result"][
                    "run_status"
                ] == "cancelled"
                assert events.count("tool.cancelled") == 1
                assert token not in str(ctx.snapshot())
        finally:
            await host.stop()

    asyncio.run(scenario())
