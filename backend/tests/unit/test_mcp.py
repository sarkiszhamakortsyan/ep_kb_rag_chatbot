import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from mcp import Client

from app.core.config import Settings
from app.main import create_app
from app.mcp.server import build_mcp_server
from app.services import Services, create_services
from app.stores.events.base import EventStore
from tests.fakes import FakeEmbedder, FakeLLM

pytestmark = pytest.mark.anyio

TOKEN = "mcp-test-token-0123456789"


def make_settings(tmp_path: Path, **overrides: object) -> Settings:
    kb = tmp_path / "kb"
    kb.mkdir(exist_ok=True)
    (kb / "kb-1.md").write_text(
        "---\nid: kb-1\ntitle: Backup guide\n---\n## Backups\n\nBackups are retained for 35 days.\n"
    )
    values: dict[str, object] = {
        "kb_dir": kb,
        "index_dir": tmp_path / "index",
        "database_path": tmp_path / "db" / "history.sqlite",
        "min_score": 0.0,
        "enabled_llm_providers": ["ollama"],
        "llm_provider": "ollama",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[call-arg, arg-type]


async def fake_services(settings: Settings, events: EventStore | None = None) -> Services:
    return await create_services(
        settings,
        events,
        llm_factories={
            "ollama": lambda s: FakeLLM("Backups are retained for 35 days [1].", name="ollama")
        },
        embedding_factories={"ollama": lambda s: FakeEmbedder()},
    )


def payload(result: Any) -> Any:
    return json.loads(result.content[0].text)


def items(result: Any) -> list[Any]:
    """A list result comes back as one content block per item."""
    return [json.loads(block.text) for block in result.content]


async def test_tools_and_resources(tmp_path: Path) -> None:
    services = await fake_services(make_settings(tmp_path))
    server = build_mcp_server(lambda: services)
    try:
        async with Client(server) as client:
            tools = {t.name for t in (await client.list_tools()).tools}
            assert tools == {"search_knowledge_base", "ask_knowledge_base"}

            found = items(await client.call_tool("search_knowledge_base", {"query": "backups"}))
            assert found[0]["doc_id"] == "kb-1" and "35 days" in found[0]["text"]

            answer = payload(await client.call_tool("ask_knowledge_base", {"question": "Backups?"}))
            assert answer["answer"] == "Backups are retained for 35 days [1]."
            assert answer["refused"] is False and answer["citations"][0]["doc_id"] == "kb-1"

            bad = await client.call_tool("ask_knowledge_base", {"question": "q", "language": "xx"})
            assert bad.is_error and "Unsupported language" in bad.content[0].text
            wrong_model = await client.call_tool(
                "ask_knowledge_base", {"question": "q", "model": "gpt"}
            )
            assert wrong_model.is_error and "gpt" in wrong_model.content[0].text

            listing = json.loads((await client.read_resource("kb://documents")).contents[0].text)
            assert listing == [
                {"doc_id": "kb-1", "title": "Backup guide", "uri": "kb://documents/kb-1"}
            ]
            article = (await client.read_resource("kb://documents/kb-1")).contents[0].text
            assert article.startswith("# Backup guide") and "35 days" in article
    finally:
        await services.aclose()


async def test_model_accepts_chat_and_cli_names(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    services = await create_services(
        settings,
        llm_factories={
            "ollama": lambda s: FakeLLM("Backups are retained for 35 days [1].", name="ollama",
                                        model="ministral-3:3b")
        },
        embedding_factories={"ollama": lambda s: FakeEmbedder()},
    )  # fmt: skip
    try:
        async with Client(build_mcp_server(lambda: services)) as client:
            for name in ("ollama", "local", "/local", "Ministral", "ministral-3:3b"):
                result = await client.call_tool(
                    "ask_knowledge_base", {"question": "Backups?", "model": name}
                )
                assert not result.is_error, name
                assert payload(result)["model"] == "ministral-3:3b"

            wrong = await client.call_tool("ask_knowledge_base", {"question": "q", "model": "gpt"})
            text = wrong.content[0].text
            assert wrong.is_error and "'gpt'" in text and "ministral-3:3b" in text
            # A known but disabled model gets the pipeline's own explanation.
            disabled = await client.call_tool(
                "ask_knowledge_base", {"question": "q", "model": "claude"}
            )
            assert disabled.is_error and "anthropic" in disabled.content[0].text
    finally:
        await services.aclose()


async def test_prompts_turn_a_question_into_a_tool_request(tmp_path: Path) -> None:
    services = await fake_services(make_settings(tmp_path))
    try:
        async with Client(build_mcp_server(lambda: services)) as client:
            prompts = {p.name: p for p in (await client.list_prompts()).prompts}
            assert set(prompts) == {"ask", "ask_claude", "ask_local"}
            assert [a.name for a in prompts["ask"].arguments or []] == ["question"]

            question = "How long are backups kept?"
            ask = await client.get_prompt("ask", {"question": question})
            text = ask.messages[0].content.text  # type: ignore[union-attr]
            assert text.startswith(
                "Answer this question with the omnicorp-kb tool ask_knowledge_base."
            )
            assert text.endswith(f"Question: {question}")

            claude = await client.get_prompt("ask_claude", {"question": question})
            assert 'model "anthropic"' in claude.messages[0].content.text  # type: ignore[union-attr]
            local = await client.get_prompt("ask_local", {"question": question})
            assert 'model "ollama"' in local.messages[0].content.text  # type: ignore[union-attr]
    finally:
        await services.aclose()


async def test_tools_explain_when_the_index_is_not_ready() -> None:
    def not_ready() -> Services:
        raise RuntimeError("The knowledge base is still loading.")

    async with Client(build_mcp_server(not_ready)) as client:
        result = await client.call_tool("search_knowledge_base", {"query": "x"})
        assert result.is_error and "still loading" in result.content[0].text


INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "test", "version": "1"},
    },
}
HEADERS = {"Accept": "application/json, text/event-stream", "Host": "localhost:8080"}


def test_http_endpoint_requires_the_token(tmp_path: Path) -> None:
    app = create_app(
        make_settings(tmp_path, mcp_token=TOKEN), fake_services, load_in_background=False
    )
    with TestClient(app, base_url="http://localhost:8080") as client:
        denied = client.post("/api/mcp/", json=INITIALIZE, headers=HEADERS)
        assert denied.status_code == 401 and denied.json()["error"]["code"] == "unauthorized"
        wrong = client.post(
            "/api/mcp/", json=INITIALIZE, headers={**HEADERS, "Authorization": "Bearer nope"}
        )
        assert wrong.status_code == 401

        ok = client.post(
            "/api/mcp/", json=INITIALIZE, headers={**HEADERS, "Authorization": f"Bearer {TOKEN}"}
        )
        assert ok.status_code == 200
        assert "omnicorp-knowledge-base" in ok.text


def test_http_endpoint_is_off_without_a_token(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path), fake_services, load_in_background=False)
    with TestClient(app) as client:
        assert client.post("/api/mcp/", json=INITIALIZE, headers=HEADERS).status_code == 404
