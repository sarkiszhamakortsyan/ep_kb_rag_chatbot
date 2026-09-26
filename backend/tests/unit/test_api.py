import asyncio
import json
from collections.abc import AsyncIterator, Callable, Iterator, Sequence
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.v1 import health, providers
from app.api.v1.health import OllamaStatus
from app.core.config import Settings
from app.main import create_app
from app.providers.errors import ProviderUnavailableError
from app.providers.llm.base import (
    ChatMessage,
    GenerationOptions,
    LLMProvider,
    StreamEvent,
    TextDelta,
)
from app.providers.llm.registry import DEFAULT_FACTORIES as REAL_LLM_FACTORIES
from app.services import Services, create_services
from app.stores.events.base import EventStore
from tests.fakes import FakeEmbedder, FakeLLM

KB = {
    "kb-1": "## Backups\n\nBackups are retained for 35 days in the same region.",
    "kb-2": "## Webhooks\n\nWebhooks are signed with HMAC-SHA256 and retried 8 times.",
}


class FailingLLM(FakeLLM):
    """Streams one token, then fails: exercises the SSE error path."""

    async def stream(
        self,
        system: str,
        messages: Sequence[ChatMessage],
        options: GenerationOptions | None = None,
    ) -> AsyncIterator[StreamEvent]:
        yield TextDelta("Partial")
        raise ProviderUnavailableError("Anthropic is busy")


@pytest.fixture(autouse=True)
def no_real_ollama(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_status(settings: Settings) -> OllamaStatus:
        return OllamaStatus(reachable=True, models=["gemma3:4b", "embeddinggemma:latest"])

    monkeypatch.setattr(health, "ollama_status", fake_status)
    monkeypatch.setattr(providers, "ollama_status", fake_status)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    kb = tmp_path / "kb"
    kb.mkdir()
    for doc_id, body in KB.items():
        (kb / f"{doc_id}.md").write_text(f"---\nid: {doc_id}\ntitle: {doc_id} guide\n---\n{body}\n")
    return Settings(  # type: ignore[call-arg]
        _env_file=None,
        kb_dir=kb,
        index_dir=tmp_path / "index",
        top_k=2,
        min_score=0.3,
        ollama_base_url="http://127.0.0.1:9",
        database_path=tmp_path / "db" / "history.sqlite",
    )


def factory(
    llms: dict[str, Callable[[Settings], LLMProvider]],
) -> Callable[[Settings], "asyncio.Future[Services]"]:
    async def build(settings: Settings, events: EventStore) -> Services:
        return await create_services(
            settings,
            events,
            llm_factories=llms,
            embedding_factories={"ollama": lambda s: FakeEmbedder()},
        )

    return build  # type: ignore[return-value]


def client_for(
    settings: Settings, llms: dict[str, Callable[[Settings], LLMProvider]]
) -> Iterator[TestClient]:
    app = create_app(settings, factory(llms), load_in_background=False)
    with TestClient(app) as client:
        yield client


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    yield from client_for(
        settings,
        {
            "ollama": lambda s: FakeLLM("Backups are retained for 35 days [1].", name="ollama"),
            "anthropic": REAL_LLM_FACTORIES["anthropic"],  # no key configured
        },
    )


def sse_events(text: str) -> list[tuple[str, dict[str, object]]]:
    events = []
    for block in text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((lines["event"], json.loads(lines["data"])))
    return events


# --- health & providers ---------------------------------------------------------------------


def test_health_reports_ready_index(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "ok" and body["ready"] is True
    assert body["index"] == {
        "ready": True,
        "documents": 2,
        "chunks": 2,
        "embedding_model": "fake:fake-embed",
        "error": None,
    }


def test_request_id_is_generated_or_echoed(client: TestClient) -> None:
    assert len(client.get("/api/v1/health").headers["x-request-id"]) == 32
    echoed = client.get("/api/v1/health", headers={"X-Request-ID": "abc-123"})
    assert echoed.headers["x-request-id"] == "abc-123"


def test_providers_lists_availability(client: TestClient) -> None:
    body = client.get("/api/v1/providers").json()
    assert body["default"] == "ollama"
    by_name = {p["name"]: p for p in body["providers"]}
    assert by_name["ollama"]["available"] and by_name["ollama"]["default"]
    assert not by_name["anthropic"]["available"]
    assert "ANTHROPIC_API_KEY" in by_name["anthropic"]["detail"]


# --- /chat ----------------------------------------------------------------------------------


def test_chat_answers_with_citations(client: TestClient) -> None:
    response = client.post(
        "/api/v1/chat",
        json={"message": "How long are backups retained?", "conversation_id": "conv_1"},
    )
    body = response.json()
    assert response.status_code == 200
    assert body["answer"] == "Backups are retained for 35 days [1]."
    assert body["conversation_id"] == "conv_1"
    assert body["refused"] is False and body["provider"] == "ollama"
    assert [(c["number"], c["doc_id"], c["section"]) for c in body["citations"]] == [
        (1, "kb-1", "Backups")
    ]
    assert body["usage"]["output_tokens"] > 0
    assert body["timings"]["total_ms"] >= 0


def test_off_topic_question_is_refused_without_llm(client: TestClient) -> None:
    body = client.post("/api/v1/chat", json={"message": "zebra quantum football"}).json()
    assert body["refused"] is True and body["refusal_reason"] == "low_score"
    assert body["provider"] is None and body["citations"] == []


@pytest.mark.parametrize(
    ("payload", "fragment"),
    [
        ({"message": "   "}, "message"),
        ({"message": "x" * 4001}, "message"),
        ({}, "message"),
        ({"message": "hi", "options": {"language": "de"}}, "options.language"),
        ({"message": "hi", "conversation_id": "../etc"}, "conversation_id"),
    ],
)
def test_invalid_requests_are_rejected(
    client: TestClient, payload: dict[str, object], fragment: str
) -> None:
    response = client.post("/api/v1/chat", json=payload)
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error" and fragment in error["message"]


def test_unknown_provider_is_a_400(client: TestClient) -> None:
    response = client.post(
        "/api/v1/chat", json={"message": "backups?", "options": {"provider": "gpt"}}
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_provider"


def test_unconfigured_provider_is_a_503(client: TestClient) -> None:
    response = client.post(
        "/api/v1/chat",
        json={"message": "How long are backups retained?", "options": {"provider": "anthropic"}},
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "provider_not_configured"


def test_provider_outage_is_a_503(settings: Settings) -> None:
    for client in client_for(
        settings,
        {
            "ollama": lambda s: FailingLLM(name="ollama"),
            "anthropic": REAL_LLM_FACTORIES["anthropic"],
        },
    ):
        response = client.post("/api/v1/chat", json={"message": "How long are backups retained?"})
        assert response.status_code == 503
        assert response.json()["error"] == {
            "code": "provider_unavailable",
            "message": "Anthropic is busy",
        }


# --- /chat/stream ---------------------------------------------------------------------------


def test_stream_sends_meta_tokens_and_done(client: TestClient) -> None:
    response = client.post(
        "/api/v1/chat/stream", json={"message": "How long are backups retained?"}
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = sse_events(response.text)

    assert events[0][0] == "meta"
    meta = events[0][1]
    assert [s["doc_id"] for s in meta["sources"]] == ["kb-1"]  # type: ignore[index]
    tokens = "".join(str(data["text"]) for name, data in events if name == "token")
    assert tokens == "Backups are retained for 35 days [1]."
    name, done = events[-1]
    assert name == "done" and done["message_id"] == meta["message_id"]
    assert done["citations"][0]["doc_id"] == "kb-1"  # type: ignore[index]


def test_stream_reports_errors_as_events(settings: Settings) -> None:
    for client in client_for(
        settings,
        {
            "ollama": lambda s: FailingLLM(name="ollama"),
            "anthropic": REAL_LLM_FACTORIES["anthropic"],
        },
    ):
        response = client.post(
            "/api/v1/chat/stream", json={"message": "How long are backups retained?"}
        )
        events = sse_events(response.text)
        assert [name for name, _ in events] == ["meta", "token", "error"]
        assert events[-1][1] == {"code": "provider_unavailable", "message": "Anthropic is busy"}


def test_stream_rejects_invalid_provider_before_streaming(client: TestClient) -> None:
    response = client.post(
        "/api/v1/chat/stream", json={"message": "hi", "options": {"provider": "gpt"}}
    )
    assert response.status_code == 400


# --- startup --------------------------------------------------------------------------------


def test_config_error_at_startup_is_reported_not_retried(settings: Settings) -> None:
    # "anthropic" is enabled in the settings but has no factory: a configuration error.
    for client in client_for(settings, {"ollama": lambda s: FakeLLM(name="ollama")}):
        health_body = client.get("/api/v1/health").json()
        assert health_body["status"] == "degraded" and health_body["ready"] is False
        assert "UnknownProviderError" in health_body["index"]["error"]
        response = client.post("/api/v1/chat", json={"message": "hi"})
        assert response.status_code == 503
        assert "failed to load" in response.json()["error"]["message"]


def test_chat_is_503_while_index_is_loading(settings: Settings) -> None:
    release = asyncio.Event()

    async def slow_factory(s: Settings, events: EventStore) -> Services:
        await release.wait()
        raise AssertionError("never reached in this test")

    app = create_app(settings, slow_factory, load_in_background=True)
    with TestClient(app) as client:
        health_body = client.get("/api/v1/health").json()
        assert health_body["status"] == "starting" and health_body["ready"] is False
        response = client.post("/api/v1/chat", json={"message": "hi"})
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "not_ready"


def test_openapi_documents_the_endpoints(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert {"/api/v1/health", "/api/v1/providers", "/api/v1/chat", "/api/v1/chat/stream"} <= set(
        paths
    )
