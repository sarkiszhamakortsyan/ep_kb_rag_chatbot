from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.services import Services, create_services
from app.stores.events.base import EventStore
from tests.fakes import FakeEmbedder, FakeLLM

TOKEN = "test-admin-token-0123456789"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


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
        "admin_token": TOKEN,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[call-arg, arg-type]


async def fake_services(settings: Settings, events: EventStore) -> Services:
    return await create_services(
        settings,
        events,
        llm_factories={
            "ollama": lambda s: FakeLLM("Backups are retained for 35 days [1].", name="ollama")
        },
        embedding_factories={"ollama": lambda s: FakeEmbedder()},
    )


def client_with(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings, fake_services, load_in_background=False)) as client:
        yield client


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    yield from client_with(make_settings(tmp_path))


def ask(client: TestClient, message: str) -> dict[str, object]:
    response = client.post("/api/v1/chat", json={"message": message})
    assert response.status_code == 200
    body: dict[str, object] = response.json()
    return body


# --- access control ---------------------------------------------------------------------------


def test_admin_is_disabled_without_a_token(tmp_path: Path) -> None:
    for client in client_with(make_settings(tmp_path, admin_token=None)):
        response = client.get("/api/v1/admin/session", headers=AUTH)
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "admin_disabled"


@pytest.mark.parametrize(
    "headers",
    [{}, {"Authorization": "Bearer wrong"}, {"Authorization": TOKEN}, {"Authorization": "Basic x"}],
)
def test_admin_rejects_missing_or_wrong_tokens(client: TestClient, headers: dict[str, str]) -> None:
    response = client.get("/api/v1/admin/history", headers=headers)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_session_reports_the_history_settings(client: TestClient) -> None:
    body = client.get("/api/v1/admin/session", headers=AUTH).json()
    assert body == {"history_enabled": True, "history_retention_days": 90}


# --- history ----------------------------------------------------------------------------------


def test_chat_turns_appear_in_the_history(client: TestClient) -> None:
    first = ask(client, "How long are backups kept?")
    ask(client, "Where are backups stored?")

    page = client.get("/api/v1/admin/history", headers=AUTH).json()
    assert page["total"] == 2 and page["limit"] == 50 and page["offset"] == 0
    assert [t["question"] for t in page["items"]] == [
        "Where are backups stored?",
        "How long are backups kept?",
    ]
    assert page["items"][1]["sources"] == 1 and page["items"][1]["provider"] == "ollama"

    detail = client.get(f"/api/v1/admin/history/{first['message_id']}", headers=AUTH).json()
    assert detail["answer"] == "Backups are retained for 35 days [1]."
    assert detail["citations"][0]["doc_id"] == "kb-1"
    assert detail["conversation_id"] == first["conversation_id"]


def test_history_filters_and_paging(client: TestClient) -> None:
    ask(client, "How long are backups kept?")
    ask(client, "Is the webhook signed?")

    page = client.get("/api/v1/admin/history?q=webhook&limit=1", headers=AUTH).json()
    assert page["total"] == 1 and page["items"][0]["question"] == "Is the webhook signed?"
    assert client.get("/api/v1/admin/history?refused=true", headers=AUTH).json()["total"] == 0
    assert client.get("/api/v1/admin/history?limit=500", headers=AUTH).status_code == 422
    assert client.get("/api/v1/admin/history?from=not-a-date", headers=AUTH).status_code == 422


def test_unknown_turn_is_404(client: TestClient) -> None:
    response = client.get("/api/v1/admin/history/nope", headers=AUTH)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_csv_export(client: TestClient) -> None:
    ask(client, "How long are backups kept?")
    ask(client, "=HYPERLINK(1)")  # would run as a formula in Excel

    response = client.get("/api/v1/admin/history/export.csv", headers=AUTH)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    lines = response.content.decode("utf-8-sig").splitlines()
    assert lines[0].startswith("created_at,conversation_id,message_id,question,answer")
    assert len(lines) == 3
    assert "'=HYPERLINK(1)" in lines[1]  # neutralised
    assert "kb-1" in lines[2]


def test_history_can_be_disabled(tmp_path: Path) -> None:
    for client in client_with(make_settings(tmp_path, history_enabled=False)):
        ask(client, "How long are backups kept?")  # chat still works
        assert client.get("/api/v1/admin/session", headers=AUTH).json()["history_enabled"] is False
        response = client.get("/api/v1/admin/history", headers=AUTH)
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "history_disabled"
    assert not (tmp_path / "db").exists()


def test_history_is_available_while_the_index_loads(tmp_path: Path) -> None:
    async def never_ready(settings: Settings, events: EventStore) -> Services:
        raise RuntimeError("index failed")

    app = create_app(make_settings(tmp_path), never_ready, load_in_background=False)
    with TestClient(app) as client:
        assert client.get("/api/v1/admin/history", headers=AUTH).json()["total"] == 0


# --- statistics -------------------------------------------------------------------------------


def test_stats_endpoint(client: TestClient) -> None:
    ask(client, "How long are backups kept?")
    body = client.get("/api/v1/admin/stats", headers=AUTH).json()
    assert body["questions"] == 1 and body["answered"] == 1
    assert len(body["per_day"]) == 30  # default range: the last 30 days
    assert body["per_day"][-1]["answered"] == 1
    assert body["top_documents"][0]["doc_id"] == "kb-1"
    assert body["per_model"][0]["provider"] == "ollama"


def test_stats_rejects_bad_ranges(client: TestClient) -> None:
    for query in ("from=2026-09-10&to=2026-09-01", "from=2024-01-01&to=2026-01-01"):
        response = client.get(f"/api/v1/admin/stats?{query}", headers=AUTH)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "invalid_range"
    assert client.get("/api/v1/admin/stats").status_code == 401
