import json
from collections.abc import Callable

import anthropic
import httpx2
import pytest

from app.providers.errors import ProviderConfigError, ProviderError, ProviderUnavailableError
from app.providers.llm.anthropic import AnthropicLLMProvider
from app.providers.llm.base import ChatMessage, GenerationDone, GenerationOptions, TextDelta

pytestmark = pytest.mark.anyio

Handler = Callable[[httpx2.Request], httpx2.Response]


def sse(*events: dict[str, object]) -> bytes:
    return b"".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n".encode() for e in events)


STREAM = sse(
    {
        "type": "message_start",
        "message": {
            "id": "msg_1",
            "type": "message",
            "role": "assistant",
            "model": "claude-opus-5",
            "content": [],
            "stop_reason": None,
            "stop_sequence": None,
            "usage": {
                "input_tokens": 120,
                "output_tokens": 1,
                "cache_read_input_tokens": 100,
                "cache_creation_input_tokens": 0,
            },
        },
    },
    {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
    {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Hi"}},
    {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": " [1]"}},
    {"type": "content_block_stop", "index": 0},
    {
        "type": "message_delta",
        "delta": {"stop_reason": "end_turn", "stop_sequence": None},
        "usage": {"output_tokens": 7},
    },
    {"type": "message_stop"},
)


def provider(handler: Handler, **kwargs: object) -> AnthropicLLMProvider:
    client = anthropic.AsyncAnthropic(
        api_key="sk-test",
        max_retries=0,
        http_client=anthropic.DefaultAsyncHttpxClient(transport=httpx2.MockTransport(handler)),
    )
    return AnthropicLLMProvider(None, "claude-opus-5", client=client, **kwargs)  # type: ignore[arg-type]


async def test_streams_text_and_reports_usage() -> None:
    requests: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        return httpx2.Response(200, content=STREAM, headers={"content-type": "text/event-stream"})

    llm = provider(handler)
    events = [
        e
        async for e in llm.stream(
            "System prompt",
            [ChatMessage("user", "Question?")],
            GenerationOptions(temperature=0.7, max_output_tokens=500),
        )
    ]

    assert events[:2] == [TextDelta("Hi"), TextDelta(" [1]")]
    done = events[2]
    assert isinstance(done, GenerationDone)
    assert done.usage.input_tokens == 120
    assert done.usage.output_tokens == 7
    assert done.usage.cache_read_input_tokens == 100
    assert done.stop_reason == "end_turn"
    assert done.model == "claude-opus-5"

    body = json.loads(requests[0].content)
    assert body["model"] == "claude-opus-5"
    assert body["max_tokens"] == 500
    assert body["system"] == [
        {"type": "text", "text": "System prompt", "cache_control": {"type": "ephemeral"}}
    ]
    assert body["messages"] == [{"role": "user", "content": "Question?"}]
    assert "temperature" not in body  # rejected by current Claude models
    assert body["fallbacks"] == "default"
    assert "server-side-fallback-2026-07-01" in requests[0].headers["anthropic-beta"]
    assert "output_config" not in body


async def test_effort_and_fallback_are_configurable() -> None:
    bodies: list[dict[str, object]] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        bodies.append(json.loads(request.content))
        return httpx2.Response(200, content=STREAM, headers={"content-type": "text/event-stream"})

    llm = provider(handler, effort="low", refusal_fallback=False)
    await llm.generate("s", [ChatMessage("user", "q")])
    assert bodies[0]["output_config"] == {"effort": "low"}
    assert "fallbacks" not in bodies[0]


def error(status: int, kind: str) -> Handler:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            status, json={"type": "error", "error": {"type": kind, "message": kind}}
        )

    return handler


@pytest.mark.parametrize(
    ("status", "kind", "expected"),
    [
        (401, "authentication_error", ProviderConfigError),
        (429, "rate_limit_error", ProviderUnavailableError),
        (529, "overloaded_error", ProviderUnavailableError),
        (400, "invalid_request_error", ProviderError),
    ],
)
async def test_api_errors_are_mapped(status: int, kind: str, expected: type[Exception]) -> None:
    with pytest.raises(expected) as info:
        await provider(error(status, kind)).generate("s", [ChatMessage("user", "q")])
    if expected is ProviderError:
        assert type(info.value) is ProviderError


async def test_connection_error_is_unavailable() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("down")

    with pytest.raises(ProviderUnavailableError):
        await provider(handler).generate("s", [ChatMessage("user", "q")])


def test_missing_key_is_a_config_error() -> None:
    with pytest.raises(ProviderConfigError):
        AnthropicLLMProvider(None, "claude-opus-5")
