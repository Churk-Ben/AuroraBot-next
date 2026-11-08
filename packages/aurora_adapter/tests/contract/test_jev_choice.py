"""用模拟传输验证 Jev 类型化选择、错误隔离和资源关闭。"""

import asyncio
import json

import httpx2
import pytest
from aurora_adapter.model import ModelConfig, ModelError, ModelProtocolError
from aurora_adapter.model.adapters.jev import JevChoiceClient
from aurora_adapter.model.configuration import resolve_choice, resolve_model
from aurora_adapter.model.decisions import ChoiceRequest
from aurora_adapter.model.plugin import plugin
from aurora_config import plugin as config_plugin
from aurora_core.bootstrap import bootstrap
from aurora_core.discovery import register_plugins


def request() -> ChoiceRequest:
    return {"state": {"text": "等待核对"}, "instructions": "是否介入", "criteria": {"observe": "观察", "guide": "介入"}}


def test_jev_choice_uses_typed_endpoint_and_runtime_credential():
    async def scenario():
        seen = []

        def handle(req):
            seen.append(req)
            assert str(req.url) == "https://decision.test/v1/systemone"
            assert req.headers["authorization"] == "Bearer runtime-secret"
            body = json.loads(req.content)
            assert body == {
                "model": "jev-latest",
                "state": request()["state"],
                "questions": {
                    "decision": {"type": "choice", "instructions": "是否介入", "criteria": request()["criteria"]}
                },
            }
            return httpx2.Response(
                200,
                json={
                    "answers": {
                        "decision": {
                            "type": "choice",
                            "choice": "guide",
                            "confidence": 0.01,
                            "probabilities": {"observe": 0.99, "guide": 0.01},
                        }
                    }
                },
            )

        client = JevChoiceClient(
            ModelConfig("jev-latest", "https://decision.test"),
            api_key="runtime-secret",
            transport=httpx2.MockTransport(handle),
        )
        try:
            assert await client.choose(request()) == "guide"
            assert len(seen) == 1
        finally:
            await client.aclose()
        assert client._client.is_closed

    asyncio.run(scenario())


@pytest.mark.parametrize("status", [301, 401, 402, 422, 429, 502])
def test_http_errors_do_not_retry_follow_redirect_or_expose_body(status):
    async def scenario():
        calls = []

        def handle(req):
            calls.append(req)
            return httpx2.Response(
                status, text="runtime-secret private-state", headers={"location": "https://other.test"}
            )

        client = JevChoiceClient(
            ModelConfig("jev-latest"), api_key="runtime-secret", transport=httpx2.MockTransport(handle)
        )
        try:
            with pytest.raises(ModelError) as error:
                await client.choose(request())
            assert str(status) in str(error.value)
            assert "runtime-secret" not in str(error.value) and "private-state" not in str(error.value)
            assert len(calls) == 1
        finally:
            await client.aclose()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"answers": []},
        {"answers": {"decision": None}},
        {"answers": {"decision": {"type": "noul", "choice": "guide"}}},
        {"answers": {"decision": {"type": "choice", "choice": "undeclared"}}},
        {"answers": {"decision": {"type": "choice", "choice": 1}}},
    ],
)
def test_malformed_answers_are_not_decisions(body):
    async def scenario():
        client = JevChoiceClient(
            ModelConfig("jev-latest"),
            api_key="secret",
            transport=httpx2.MockTransport(lambda _: httpx2.Response(200, json=body)),
        )
        try:
            with pytest.raises(ModelProtocolError):
                await client.choose(request())
        finally:
            await client.aclose()

    asyncio.run(scenario())


def test_cancel_waits_for_transport_cleanup():
    async def scenario():
        entered, cleaned = asyncio.Event(), asyncio.Event()

        async def handle(req):
            try:
                entered.set()
                await asyncio.Event().wait()
            finally:
                cleaned.set()

        client = JevChoiceClient(ModelConfig("jev-latest"), api_key="secret", transport=httpx2.MockTransport(handle))
        task = asyncio.create_task(client.choose(request()))
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert cleaned.is_set()
        await client.aclose()

    asyncio.run(scenario())


def test_chat_and_choice_profiles_cannot_be_interchanged():
    registry = bootstrap()
    register_plugins(registry, (config_plugin(), plugin()))
    profiles = {
        "decision": {"adapter": "org.aurora.adapter:adapters/model/jev", "model": "jev-latest"},
        "chat": {"adapter": "org.aurora.adapter:adapters/model/litellm", "model": "test"},
    }
    bindings = {"cadence": "decision", "reasoning": "chat"}
    assert resolve_choice(registry, profiles, bindings, "cadence").profile_name == "decision"
    with pytest.raises(TypeError):
        resolve_model(registry, profiles, bindings, "cadence")
    with pytest.raises(TypeError):
        resolve_choice(registry, profiles, bindings, "reasoning")
