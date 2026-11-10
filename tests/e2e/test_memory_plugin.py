"""通过正式配置、默认 Bot 和 ReAct 工具验证记忆写入及重启后召回。"""

import asyncio
import json

import httpx
import tomli_w
from aurora_adapter.model import JsonValue
from aurora_adapter.model.config import ADAPTERS, ModelAdapter
from aurora_adapter.model.litellm import LiteLLMClient
from aurora_adapter.model.testing import FakeReply
from aurora_bot.memory import MEMORY_TOOLS
from aurora_bot.memory import plugin as memory_plugin
from aurora_core import Id
from aurora_core.registry import RegistryEntry

from tests.e2e.test_default_assembly import ADAPTER, settings, setup


def test_memory_plugin_roundtrip_restore_and_resource_ownership(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_TEST_KEY", "memory-runtime-secret")

    async def scenario():
        requests, embeddings, observations = [], [], []

        def handle(request):
            assert request.headers["authorization"] == "Bearer memory-runtime-secret"
            body = json.loads(request.content)
            requests.append(body)
            return httpx.Response(
                200, json={"data": [{"index": i, "embedding": [1, 0]} for i, _ in enumerate(body["input"])]}
            )

        async def factory(config, *, api_key=None):
            client = LiteLLMClient(
                kind="embedding", config=config, api_key=api_key, transport=httpx.MockTransport(handle)
            )
            embeddings.append(client)
            return client

        for phase in ("write", "search"):
            host, assembly, _, registry, models, _, _, _ = setup(tmp_path, extra_plugins=(memory_plugin(),))
            adapter = Id("dev.memory:adapters/embedding")
            registry.register(
                RegistryEntry(adapter, "adapter", ModelAdapter("embedding", factory), "test", register_to=ADAPTERS)
            )

            if phase == "write":
                files = {
                    "org.aurora.bot/config.toml": {
                        **settings(tools=False),
                        "tools": [
                            {"tool": str(identity), "instance_id": f"memory/{action}"}
                            for action, identity in MEMORY_TOOLS.items()
                        ],
                    },
                    "org.aurora.adapter/model/profiles.toml": {
                        "primary": {"adapter": str(ADAPTER), "model": "fake"},
                        "embedding": {
                            "adapter": str(adapter),
                            "model": "test-vector",
                            "provider": "openai",
                            "base_url": "https://embedding.test/v1",
                            "credential": "MEMORY_TEST_KEY",
                        },
                    },
                    "org.aurora.adapter/model/bindings.toml": {"reasoning": "primary", "memory": "embedding"},
                }
                for relative, value in files.items():
                    path = tmp_path / "config" / relative
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(tomli_w.dumps(value), encoding="utf-8")

            previous_requests = len(requests)
            await host.start()
            try:
                assert len(requests) == previous_requests

                def respond(request, phase=phase):
                    if request["messages"][-1]["role"] == "tool":
                        observed = json.loads(request["messages"][-1]["content"])
                        assert observed["status"] == "completed"
                        observations.append(observed["value"])
                        return FakeReply(("已记住" if phase == "write" else observed["value"]["items"][0]["text"],))
                    arguments: dict[str, JsonValue] = (
                        {"memory_id": "drink", "text": "喜欢喝茶", "source": "用户明确告知", "expected_revision": ""}
                        if phase == "write"
                        else {"query": "我偏好的饮料是什么", "top_k": 1.0}
                    )
                    return FakeReply(tool_calls=({"id": phase, "name": f"memory_{phase}", "arguments": arguments},))

                models[0].respond = respond
                result = await assembly.runtime.submit(
                    "记住我的偏好" if phase == "write" else "我偏好的饮料是什么"
                ).run.wait()
                assert result.status == "completed"
            finally:
                await host.stop()
            assert all(client._transport.is_closed() for client in embeddings)
        assert len(requests) == 2
        assert observations[1]["items"][0]["revision"] == observations[0]["revision"]
        assert observations[1]["items"][0]["text"] == "喜欢喝茶"
        snapshot = (tmp_path / "framework/ctx.json").read_text(encoding="utf-8")
        assert (
            "memory-runtime-secret" not in snapshot
            and "vectors" not in snapshot
            and "state/memory/config" not in snapshot
        )
        assert (tmp_path / "config/org.aurora.bot/memory.toml").is_file()
        assert (tmp_path / "namespaces/ns-org.aurora.bot/memory.sqlite3").is_file()

    asyncio.run(scenario())
