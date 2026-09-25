import json
from collections.abc import Callable

import httpx
import pytest

from app.providers.embeddings.base import EmbeddingDocument
from app.providers.embeddings.ollama import OllamaEmbeddingProvider
from app.providers.errors import ProviderError, ProviderUnavailableError
from app.providers.llm.base import ChatMessage, GenerationDone, GenerationOptions, TextDelta
from app.providers.llm.ollama import OllamaLLMProvider

pytestmark = pytest.mark.anyio

Handler = Callable[[httpx.Request], httpx.Response]


def client(handler: Handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url="http://ollama", transport=httpx.MockTransport(handler))


def ndjson(*chunks: dict[str, object]) -> bytes:
    return b"".join(json.dumps(c).encode() + b"\n" for c in chunks)


# --- chat --------------------------------------------------------------------


async def test_chat_streams_text_then_usage() -> None:
    requests: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(
            200,
            content=ndjson(
                {"message": {"content": "Hello"}, "done": False},
                {"message": {"content": " world"}, "done": False},
                {
                    "message": {"content": ""},
                    "done": True,
                    "done_reason": "stop",
                    "prompt_eval_count": 42,
                    "eval_count": 2,
                },
            ),
        )

    provider = OllamaLLMProvider("http://ollama", "gemma3:4b", client=client(handler))
    events = [
        e
        async for e in provider.stream(
            "Be brief.", [ChatMessage("user", "Hi")], GenerationOptions(max_output_tokens=50)
        )
    ]

    assert events[:2] == [TextDelta("Hello"), TextDelta(" world")]
    done = events[2]
    assert isinstance(done, GenerationDone)
    assert (done.usage.input_tokens, done.usage.output_tokens) == (42, 2)
    assert done.stop_reason == "end_turn"

    payload = requests[0]
    assert payload["messages"] == [
        {"role": "system", "content": "Be brief."},
        {"role": "user", "content": "Hi"},
    ]
    assert payload["options"] == {"temperature": 0.1, "num_ctx": 4096, "num_predict": 50}
    assert "think" not in payload


async def test_chat_sends_think_only_when_configured() -> None:
    payloads: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payloads.append(json.loads(request.content))
        return httpx.Response(200, content=ndjson({"done": True, "done_reason": "length"}))

    provider = OllamaLLMProvider("http://ollama", "qwen3:4b", think=False, client=client(handler))
    result = await provider.generate("s", [ChatMessage("user", "q")])
    assert payloads[0]["think"] is False
    assert result.stop_reason == "max_tokens"


async def test_chat_model_not_found_is_a_provider_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": "model 'x' not found"})

    provider = OllamaLLMProvider("http://ollama", "x", client=client(handler))
    with pytest.raises(ProviderError, match="not found") as info:
        await provider.generate("s", [ChatMessage("user", "q")])
    assert not isinstance(info.value, ProviderUnavailableError)


async def test_chat_connection_failure_is_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    provider = OllamaLLMProvider("http://ollama", "gemma3:4b", client=client(handler))
    with pytest.raises(ProviderUnavailableError, match="unreachable"):
        await provider.generate("s", [ChatMessage("user", "q")])


async def test_chat_timeout_is_explained() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out")

    provider = OllamaLLMProvider("http://ollama", "gemma3:4b", timeout_s=42, client=client(handler))
    with pytest.raises(ProviderUnavailableError, match="within 42 s"):
        await provider.generate("s", [ChatMessage("user", "q")])


async def test_chat_stream_cut_off_is_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=ndjson({"message": {"content": "Hel"}, "done": False}))

    provider = OllamaLLMProvider("http://ollama", "gemma3:4b", client=client(handler))
    with pytest.raises(ProviderUnavailableError, match="before finishing"):
        await provider.generate("s", [ChatMessage("user", "q")])


# --- embeddings ----------------------------------------------------------------


async def test_embeddings_use_model_prompts_and_batches() -> None:
    batches: list[list[str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        texts = json.loads(request.content)["input"]
        batches.append(texts)
        return httpx.Response(200, json={"embeddings": [[float(len(t))] for t in texts]})

    provider = OllamaEmbeddingProvider(
        "http://ollama", "embeddinggemma", batch_size=2, client=client(handler)
    )
    docs = [EmbeddingDocument("a", "T1"), EmbeddingDocument("bb", "T2"), EmbeddingDocument("c")]
    vectors = await provider.embed_documents(docs)
    query = await provider.embed_query("How long?")

    assert batches == [
        ["title: T1 | text: a", "title: T2 | text: bb"],
        ["title: none | text: c"],
        ["task: search result | query: How long?"],
    ]
    assert vectors == [[19.0], [20.0], [21.0]]  # input order preserved across batches
    assert query == [float(len("task: search result | query: How long?"))]


async def test_embeddings_unknown_model_uses_plain_text() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.extend(json.loads(request.content)["input"])
        return httpx.Response(200, json={"embeddings": [[0.0]]})

    provider = OllamaEmbeddingProvider("http://ollama", "all-minilm", client=client(handler))
    await provider.embed_query("plain")
    assert seen == ["plain"]


async def test_embeddings_count_mismatch_is_an_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"embeddings": []})

    provider = OllamaEmbeddingProvider("http://ollama", "embeddinggemma", client=client(handler))
    with pytest.raises(ProviderError, match="0 embeddings for 1"):
        await provider.embed_query("q")


async def test_embeddings_server_error_is_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="loading")

    provider = OllamaEmbeddingProvider("http://ollama", "embeddinggemma", client=client(handler))
    with pytest.raises(ProviderUnavailableError):
        await provider.embed_query("q")
