import io
import json
from collections.abc import Callable
from typing import Any

import httpx

from app.cli.api import KbClient
from app.cli.main import EXIT_ERROR, EXIT_NOT_COVERED, EXIT_OK, main

DONE = {
    "conversation_id": "conv1",
    "message_id": "m1",
    "answer": "Backups are kept for 35 days [1].",
    "citations": [
        {"number": 1, "chunk_id": "kb-003#001", "doc_id": "kb-003", "title": "Data policy",
         "section": "Backups", "snippet": "…", "score": 0.63},
    ],
    "refused": False,
    "refusal_reason": None,
    "provider": "anthropic",
    "model": "claude-opus-5",
    "timings": {"total_ms": 3800},
}  # fmt: skip


def sse(*events: tuple[str, Any]) -> str:
    return "".join(f"event: {e}\ndata: {json.dumps(d)}\n\n" for e, d in events)


def client_for(handler: Callable[[httpx.Request], httpx.Response]) -> KbClient:
    return KbClient(
        "http://kb", httpx.Client(transport=httpx.MockTransport(handler), base_url="http://kb")
    )


def stream_handler(
    body: str, seen: list[dict[str, Any]]
) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})

    return handler


def run(argv: list[str], client: KbClient, stdin: str = "") -> tuple[int, str]:
    out = io.StringIO()
    code = main(argv, client=client, inp=io.StringIO(stdin), out=out)
    return code, out.getvalue()


def test_ask_streams_the_answer_and_sources() -> None:
    seen: list[dict[str, Any]] = []
    body = sse(
        ("meta", {"conversation_id": "conv1", "message_id": "m1", "sources": []}),
        ("token", {"text": "Backups are kept "}),
        ("token", {"text": "for 35 days [1]."}),
        ("done", DONE),
    )
    code, text = run(
        ["ask", "How long?", "--model", "anthropic", "--language", "de", "--detailed"],
        client_for(stream_handler(body, seen)),
    )

    assert code == EXIT_OK
    assert "Backups are kept for 35 days [1]." in text
    assert "[1] Data policy \u203a Backups (kb-003)" in text
    assert "claude-opus-5 · 3.8 s" in text
    assert "\033[" not in text  # no colours when not on a terminal
    assert seen[0] == {
        "message": "How long?",
        "options": {"provider": "anthropic", "language": "de", "detail": "detailed"},
    }


def test_not_covered_exits_with_2() -> None:
    refused = {**DONE, "answer": "Not covered.", "citations": [], "refused": True, "model": None}
    body = sse(("token", {"text": "Not covered."}), ("done", refused))
    code, text = run(["ask", "Price?"], client_for(stream_handler(body, [])))
    assert code == EXIT_NOT_COVERED and "Not covered by the knowledge base." in text


def test_errors_exit_with_1() -> None:
    mid_stream = sse(
        ("token", {"text": "Part"}), ("error", {"code": "provider_unavailable", "message": "busy"})
    )
    code, text = run(["ask", "q"], client_for(stream_handler(mid_stream, [])))
    assert code == EXIT_ERROR and "Error: busy" in text

    def rejected(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400, json={"error": {"code": "invalid_provider", "message": "Unknown provider"}}
        )

    code, text = run(["ask", "q", "--model", "gpt"], client_for(rejected))
    assert code == EXIT_ERROR and "Unknown provider" in text

    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    code, text = run(["health"], client_for(down))
    assert code == EXIT_ERROR and "Cannot reach the API" in text


def test_json_output() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/chat"
        return httpx.Response(200, json=DONE)

    code, text = run(["ask", "q", "--json"], client_for(handler))
    assert code == EXIT_OK and json.loads(text)["model"] == "claude-opus-5"


def test_health_and_providers() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/health"):
            return httpx.Response(200, json={
                "status": "ok", "ready": True, "llm_provider": "ollama",
                "index": {"documents": 5, "chunks": 49},
            })  # fmt: skip
        return httpx.Response(200, json={"default": "ollama", "providers": [
            {"name": "ollama", "model": "ministral-3:3b", "default": True, "available": True},
            {"name": "anthropic", "model": "claude-opus-5", "default": False, "available": False},
        ]})  # fmt: skip

    code, text = run(["health"], client_for(handler))
    assert code == EXIT_OK and "5 documents, 49 chunks" in text
    code, text = run(["providers"], client_for(handler))
    assert "ministral-3:3b (default)" in text and "claude-opus-5 (unavailable)" in text


def test_interactive_session_keeps_the_conversation() -> None:
    seen: list[dict[str, Any]] = []
    body = sse(
        ("meta", {"conversation_id": "conv1", "message_id": "m1", "sources": []}), ("done", DONE)
    )
    script = "/model anthropic\n/lang fr\nFirst?\nSecond?\n/new\nThird?\n/lang xx\n/bogus\n/quit\n"
    code, text = run([], client_for(stream_handler(body, seen)), stdin=script)

    assert code == EXIT_OK
    assert [s.get("conversation_id") for s in seen] == [None, "conv1", None]
    assert seen[0]["options"] == {"provider": "anthropic", "language": "fr"}
    assert "Unknown language" in text and "Unknown command /bogus" in text
