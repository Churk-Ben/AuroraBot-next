"""真实 SDK 与模拟 HTTP 响应验证；不访问供应商、不需要真实密钥。"""

import asyncio
import json
from copy import deepcopy
from typing import TYPE_CHECKING, cast

import httpx
import pytest
from aurora_adapter.model import (
    ModelCapabilities,
    ModelConfig,
    ModelError,
    ModelProtocolError,
    ModelRequest,
    ToolCall,
    UnsupportedCapability,
    collect_response,
)
from aurora_adapter.model.adapters import create_litellm
from aurora_adapter.model.configuration import resolve_model
from aurora_adapter.model.plugin import plugin
from aurora_core.bootstrap import bootstrap
from aurora_core.discovery import register_plugins
from aurora_core.json_data import decode_json, encode_json

if TYPE_CHECKING:
    from aurora_adapter.model.adapters.litellm import LiteLLMClient


@pytest.fixture
def sdk(monkeypatch):
    monkeypatch.setenv("LITELLM_LOCAL_MODEL_COST_MAP", "True")
    import litellm

    return litellm


def request() -> ModelRequest:
    return {"messages": [{"role": "user", "content": "计算"}]}


def response(*, content="回答", calls=None, reason="stop"):
    return {
        "id": "response-test",
        "object": "chat.completion",
        "created": 1,
        "model": "gpt-4o-mini",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content, "tool_calls": calls},
                "finish_reason": reason,
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


def delta(*, content=None, calls=None, reason=None):
    return {"choices": [{"index": 0, "delta": {"content": content, "tool_calls": calls}, "finish_reason": reason}]}


def part(index, *, call_id=None, name=None, arguments=None):
    return {"index": index, "id": call_id, "function": {"name": name, "arguments": arguments}}


class Stream:
    def __init__(self, values, *, error=None, wait=False):
        self.values = iter(values)
        self.error = error
        self.wait = wait
        self.closed = False
        self.waiting = asyncio.Event()

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self.values)
        except StopIteration:
            pass
        if self.error:
            raise self.error
        if self.wait:
            self.waiting.set()
            await asyncio.Event().wait()
        raise StopAsyncIteration

    async def aclose(self):
        self.closed = True


def mock_completion(monkeypatch, sdk, value):
    calls = []

    async def complete(**kwargs):
        calls.append(kwargs)
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(sdk, "acompletion", complete)
    return calls


@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.parametrize("provider,model", [("openai", "Qwen/private-deployment"), ("xiaomi_mimo", "mimo-v2.5-pro")])
def test_explicit_provider_preserves_model_and_supports_custom_capabilities(sdk, streaming, provider, model):
    sent = []
    tool: ToolCall = {"id": "call_1", "name": "echo", "arguments": {"text": "验证"}}

    def handle(request):
        value = json.loads(request.content)
        sent.append(value)
        assert request.url.host == "profile.test" and request.url.path == "/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer isolated-key"
        assert value["model"] == model and value["tools"][0]["function"]["name"] == "echo"
        call = {"id": "call_1", "type": "function", "function": {"name": "echo", "arguments": '{"text":"验证"}'}}
        if not streaming:
            return httpx.Response(200, json=response(content="", calls=[call], reason="tool_calls"))
        values = [
            delta(calls=[{"index": 0, **call}]),
            delta(reason="tool_calls"),
        ]
        body = (
            "".join(
                "data: "
                + json.dumps({"id": "r", "created": 1, "object": "chat.completion.chunk", "model": model, **item})
                + "\n\n"
                for item in values
            )
            + "data: [DONE]\n\n"
        )
        return httpx.Response(200, content=body.encode(), headers={"content-type": "text/event-stream"})

    async def scenario():
        client = cast(
            "LiteLLMClient",
            await create_litellm(
                ModelConfig(
                    model, "https://profile.test/v1", provider=provider, capabilities=ModelCapabilities(True, True)
                ),
                api_key="isolated-key",
            ),
        )
        await client._transport._client.aclose()
        http = httpx.AsyncClient(transport=httpx.MockTransport(handle))
        client._transport._client = http
        request = {
            "messages": [{"role": "user", "content": "调用工具"}],
            "tools": [{"name": "echo", "description": "回显", "parameters": {"type": "object"}}],
        }
        try:
            if streaming:
                async with client.stream(cast(ModelRequest, request)) as chunks:
                    result = await collect_response(chunks)
            else:
                result = await client.complete(cast(ModelRequest, request))
            assert result["tool_calls"] == [tool] and result["finish_reason"] == "tool_calls"
            assert len(sent) == 1
        finally:
            await client.aclose()
        assert http.is_closed

    asyncio.run(scenario())


def test_profile_credentials_addresses_and_capabilities_are_isolated(sdk):
    async def scenario():
        clients = []
        transports = []
        sent = []
        try:
            for label, enabled in (("one", True), ("two", False)):
                client = cast(
                    "LiteLLMClient",
                    await create_litellm(
                        ModelConfig(
                            "team/shared-name",
                            f"https://{label}.test/v1",
                            provider="openai",
                            capabilities=ModelCapabilities(enabled, enabled),
                        ),
                        api_key=f"key-{label}",
                    ),
                )
                clients.append(client)
                await client._transport._client.aclose()

                def handle(request):
                    sent.append(
                        (request.url.host, request.headers["authorization"], json.loads(request.content)["model"])
                    )
                    return httpx.Response(200, json=response())

                http = httpx.AsyncClient(transport=httpx.MockTransport(handle))
                transports.append(http)
                client._transport._client = http
            assert clients[0].capabilities == ModelCapabilities(True, True)
            assert clients[1].capabilities == ModelCapabilities(False, False)
            assert not sdk.supports_function_calling("team/shared-name", custom_llm_provider="openai")
            await clients[0].complete(request())
            await clients[0].aclose()
            assert transports[0].is_closed and not transports[1].is_closed
            with pytest.raises(UnsupportedCapability):
                async with clients[1].stream(request()):
                    pytest.fail("显式禁用流式应拒绝")
            await clients[1].complete(request())
            assert sent == [
                ("one.test", "Bearer key-one", "team/shared-name"),
                ("two.test", "Bearer key-two", "team/shared-name"),
            ]
        finally:
            for client in clients:
                await client.aclose()
        assert all(http.is_closed for http in transports)

    asyncio.run(scenario())


def test_explicit_provider_retains_catalog_defaults_and_unknown_capabilities_stay_disabled(sdk):
    async def scenario():
        for model, capabilities in (
            ("gpt-4o-mini", ModelCapabilities(True, True)),
            ("team/unknown", ModelCapabilities(False, False)),
        ):
            client = await create_litellm(ModelConfig(model, provider="openai"), api_key="test-only")
            try:
                assert client.capabilities == capabilities
            finally:
                await client.aclose()

    asyncio.run(scenario())


@pytest.mark.parametrize("provider", ["openai", "deepseek"])
def test_registered_factory_uses_real_sdk_and_maps_tool_history(sdk, provider):
    registry = bootstrap()
    register_plugins(registry, (plugin(),))
    resolved = resolve_model(
        registry,
        {
            "main": {
                "adapter": "org.aurora.adapter:adapters/model/litellm",
                "model": "openai/gpt-4o-mini" if provider == "openai" else "deepseek/deepseek-flash",
            }
        },
        {"reasoning": "main"},
        "reasoning",
    )
    sent = []
    call: ToolCall = {"id": "call_1", "name": "add", "arguments": {"a": 1}}

    def handle(value):
        sent.append(json.loads(value.content))
        if provider == "deepseek":
            assert value.url.host == "api.deepseek.com"
            assert sent[-1]["thinking"] == {"type": "disabled"}
        return httpx.Response(200, json=response())

    async def scenario():
        client = cast("LiteLLMClient", await resolved.factory(resolved.config, api_key="test-only"))
        # 直接替换测试实例的传输，真实 LiteLLM 与 OpenAI SDK 转换仍参与执行。
        await client._transport._client.aclose()
        http = httpx.AsyncClient(transport=httpx.MockTransport(handle))
        client._transport._client = http
        value = request()
        value["tools"] = [{"name": "add", "description": "求和", "parameters": {"type": "object"}}]
        value["messages"] += [
            {"role": "assistant", "content": "", "tool_calls": [call]},
            {"role": "tool", "content": "1", "tool_call_id": "call_1"},
        ]
        before = deepcopy(value)
        try:
            result = await client.complete(value)
            assert result == {"text": "回答", "tool_calls": [], "finish_reason": "stop"}
            assert decode_json(encode_json(result)) == result
            assert value == before
            assert sent[0]["tools"][0]["function"] == value["tools"][0]
            outgoing = sent[0]["messages"][1]["tool_calls"][0]
            assert outgoing["id"] == "call_1" and json.loads(outgoing["function"]["arguments"]) == {"a": 1}
        finally:
            await client.aclose()
        assert http.is_closed

    asyncio.run(scenario())


@pytest.mark.parametrize("provider", ["openai", "anthropic", "deepseek"])
def test_real_sdk_streaming_and_owned_transport_close(sdk, provider):
    if provider != "anthropic":
        model = "openai/gpt-4o-mini" if provider == "openai" else "deepseek/deepseek-flash"
        values = [
            {"id": "r", "object": "chat.completion.chunk", "created": 1, "model": "gpt-4o-mini", **item}
            for item in [delta(content="一"), delta(content="二"), delta(reason="stop")]
        ]
        body = "".join(f"data: {json.dumps(item)}\n\n" for item in values) + "data: [DONE]\n\n"
    else:
        model = "anthropic/claude-sonnet-4-5"
        events = [
            {
                "type": "message_start",
                "message": {
                    "id": "msg_1",
                    "type": "message",
                    "role": "assistant",
                    "model": model.split("/")[1],
                    "content": [],
                    "stop_reason": None,
                    "stop_sequence": None,
                    "usage": {"input_tokens": 1, "output_tokens": 0},
                },
            },
            {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
            {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "一二"}},
            {"type": "content_block_stop", "index": 0},
            {"type": "message_delta", "delta": {"stop_reason": "end_turn"}, "usage": {"output_tokens": 2}},
            {"type": "message_stop"},
        ]
        body = "".join(f"event: {item['type']}\ndata: {json.dumps(item)}\n\n" for item in events)

    def handle(value):
        assert value.url.host == "model.test"
        if provider == "deepseek":
            assert json.loads(value.content)["thinking"] == {"type": "disabled"}
        return httpx.Response(200, content=body.encode(), headers={"content-type": "text/event-stream"})

    async def scenario():
        client = cast(
            "LiteLLMClient", await create_litellm(ModelConfig(model, "https://model.test/v1"), api_key="test-only")
        )
        transport = client._transport
        original = transport._client if provider == "openai" else transport.client
        await original.aclose()
        http = httpx.AsyncClient(transport=httpx.MockTransport(handle))
        transport._client = http
        try:
            async with client.stream(request()) as chunks:
                assert await collect_response(chunks) == {"text": "一二", "tool_calls": [], "finish_reason": "stop"}
        finally:
            await client.aclose()
        assert http.is_closed

    asyncio.run(scenario())


def test_interleaved_tool_fragments_are_complete_and_sorted(sdk, monkeypatch):
    stream = Stream(
        [
            delta(content="检查", calls=[part(1, call_id="b", name="se", arguments='{"b":')]),
            delta(
                calls=[part(0, call_id="a", name="first", arguments='{"a":1}'), part(1, name="cond", arguments="2}")]
            ),
            delta(reason="tool_calls"),
            delta(),
            {"choices": [], "usage": {"total_tokens": 4}},
        ]
    )
    calls = mock_completion(monkeypatch, sdk, stream)

    async def scenario():
        client = await create_litellm(ModelConfig("openai/gpt-4o-mini"), api_key="test-only")
        try:
            async with client.stream(request()) as chunks:
                assert await anext(chunks) == {"type": "text", "text": "检查"}
                result = await collect_response(chunks)
            assert result["tool_calls"] == [
                {"id": "a", "name": "first", "arguments": {"a": 1}},
                {"id": "b", "name": "second", "arguments": {"b": 2}},
            ]
            assert result["finish_reason"] == "tool_calls" and stream.closed
            assert calls[0]["num_retries"] == 0 and calls[0]["caching"] is False
        finally:
            await client.aclose()

    asyncio.run(scenario())


@pytest.mark.parametrize("arguments", ['{"a":', "[]", '{"a":1,"a":2}', '{"a":NaN}', '{"a":1e999}'])
@pytest.mark.parametrize("streaming", [True, False])
def test_invalid_tool_arguments_never_escape_as_a_tool_call(sdk, monkeypatch, arguments, streaming):
    value = Stream([delta(calls=[part(0, call_id="a", name="add", arguments=arguments)]), delta(reason="tool_calls")])
    if not streaming:
        value = response(calls=[{"id": "a", "function": {"name": "add", "arguments": arguments}}], reason="tool_calls")
    mock_completion(monkeypatch, sdk, value)

    async def scenario():
        client = await create_litellm(ModelConfig("openai/gpt-4o-mini"), api_key="test-only")
        try:
            with pytest.raises(ModelProtocolError):
                if streaming:
                    async with client.stream(request()) as chunks:
                        await anext(chunks)
                else:
                    await client.complete(request())
            if streaming:
                assert isinstance(value, Stream)
                assert value.closed
        finally:
            await client.aclose()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "values",
    [
        [delta(content="不完整")],
        [delta(reason="unknown")],
        [delta(reason="stop"), delta(content="结束之后")],
        [delta(reason="tool_calls")],
        [delta(calls=[part(-1, call_id="a", name="add", arguments="{}")]), delta(reason="tool_calls")],
        [
            delta(
                calls=[
                    part(0, call_id="a", name="add", arguments="{}"),
                    part(1, call_id="a", name="add", arguments="{}"),
                ]
            ),
            delta(reason="tool_calls"),
        ],
    ],
)
def test_invalid_stream_termination_or_identity_fails(sdk, monkeypatch, values):
    stream = Stream(values)
    mock_completion(monkeypatch, sdk, stream)

    async def scenario():
        client = await create_litellm(ModelConfig("openai/gpt-4o-mini"), api_key="test-only")
        try:
            with pytest.raises(ModelProtocolError):
                async with client.stream(request()) as chunks:
                    await collect_response(chunks)
            assert stream.closed
        finally:
            await client.aclose()

    asyncio.run(scenario())


@pytest.mark.parametrize("reason", ["stop", "length", "content_filter"])
def test_finish_reasons_are_preserved(sdk, monkeypatch, reason):
    mock_completion(monkeypatch, sdk, response(reason=reason))

    async def scenario():
        client = await create_litellm(ModelConfig("openai/gpt-4o-mini"), api_key="test-only")
        try:
            assert (await client.complete(request()))["finish_reason"] == reason
        finally:
            await client.aclose()

    asyncio.run(scenario())


def test_capability_rejection_precedes_sdk_and_instances_close_independently(sdk, monkeypatch):
    calls = mock_completion(monkeypatch, sdk, response())

    async def scenario():
        first = await create_litellm(ModelConfig("openai/gpt-4o-mini"), api_key="test-only")
        second = await create_litellm(ModelConfig("openai/gpt-4o-mini"), api_key="test-only")
        cast("LiteLLMClient", first).capabilities = ModelCapabilities(streaming=False, tool_calls=False)
        try:
            with pytest.raises(UnsupportedCapability):
                async with first.stream(request()):
                    pytest.fail("不支持流式")
            with pytest.raises(UnsupportedCapability):
                await first.complete({"messages": [{"role": "tool", "content": "1", "tool_call_id": "a"}]})
            assert not calls
            await first.aclose()
            await first.aclose()
            with pytest.raises(ModelError, match="已关闭"):
                await first.complete(request())
            assert (await second.complete(request()))["text"] == "回答"
        finally:
            await first.aclose()
            await second.aclose()

    asyncio.run(scenario())


@pytest.mark.parametrize("mode", ["early", "cancel", "timeout", "consumer_error"])
def test_stream_exit_always_releases_response(sdk, monkeypatch, mode):
    stream = Stream([delta(content="部分")], wait=True)
    mock_completion(monkeypatch, sdk, stream)

    async def scenario():
        client = await create_litellm(ModelConfig("openai/gpt-4o-mini"), api_key="test-only")

        async def consume():
            async with client.stream(request()) as chunks:
                assert await anext(chunks) == {"type": "text", "text": "部分"}
                with pytest.raises(ModelError, match="在途"):
                    await client.aclose()
                with pytest.raises(ModelError, match="并发"):
                    await client.complete(request())
                if mode == "early":
                    return
                if mode == "consumer_error":
                    raise ValueError("消费方错误")
                await anext(chunks)

        try:
            if mode == "early":
                await consume()
            elif mode == "consumer_error":
                with pytest.raises(ValueError, match="消费方"):
                    await consume()
            elif mode == "timeout":
                with pytest.raises(TimeoutError):
                    async with asyncio.timeout(0.02):
                        await consume()
            else:
                task = asyncio.create_task(consume())
                await stream.waiting.wait()
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
            assert stream.closed
        finally:
            await client.aclose()

    asyncio.run(scenario())


@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.parametrize("timeout", [False, True])
def test_sdk_errors_are_mapped_without_payload_or_credentials(sdk, monkeypatch, streaming, timeout):
    error = (sdk.Timeout if timeout else sdk.AuthenticationError)(
        message="secret-and-request", model="gpt-4o-mini", llm_provider="openai"
    )
    stream = Stream([delta(content="部分")], error=error)
    mock_completion(monkeypatch, sdk, stream if streaming else error)

    async def scenario():
        client = await create_litellm(ModelConfig("openai/gpt-4o-mini"), api_key="test-only")
        try:
            with pytest.raises(TimeoutError if timeout else ModelError) as caught:
                if streaming:
                    async with client.stream(request()) as chunks:
                        assert await anext(chunks) == {"type": "text", "text": "部分"}
                        await anext(chunks)
                else:
                    await client.complete(request())
            assert "secret-and-request" not in str(caught.value)
            if streaming:
                assert stream.closed
        finally:
            await client.aclose()

    asyncio.run(scenario())
