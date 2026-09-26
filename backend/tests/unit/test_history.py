from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from app.providers.llm.base import Usage
from app.rag.citations import Citation
from app.rag.pipeline import ChatResult, Timings
from app.stores.history.sqlite import HistoryFilter, SqliteHistory

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)


def result(
    message_id: str,
    question: str = "How long are backups kept?",
    *,
    refused: bool = False,
    provider: str | None = "ollama",
) -> ChatResult:
    citations = (
        []
        if refused
        else [Citation(1, "kb-003#001", "kb-003", "Data policy", "Backups", "Kept 35 days.", 0.7)]
    )
    return ChatResult(
        conversation_id="conv-1",
        message_id=message_id,
        question=question,
        answer="Not covered." if refused else "Backups are kept for 35 days [1].",
        citations=citations,
        refused=refused,
        refusal_reason="no_citations" if refused else None,
        provider=provider,
        model="ministral-3:3b" if provider else None,
        usage=Usage(input_tokens=1200, output_tokens=60, cache_read_input_tokens=10),
        timings=Timings(embed_ms=50, search_ms=1, time_to_first_token_ms=900, total_ms=1500),
        top_score=0.63,
        sources_used=6,
    )


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock(NOW)


@pytest.fixture
def history(tmp_path: Path, clock: Clock) -> SqliteHistory:
    store = SqliteHistory(tmp_path / "db" / "history.sqlite", retention_days=90, clock=clock)
    store.open()
    yield store  # type: ignore[misc]
    store.close()


async def test_records_and_reads_back_a_turn(history: SqliteHistory) -> None:
    await history.record(result("m1"))

    turn = await history.get_turn("m1")
    assert turn is not None
    assert turn.question == "How long are backups kept?"
    assert turn.answer.startswith("Backups are kept")
    assert turn.citations[0]["doc_id"] == "kb-003"
    assert turn.input_tokens == 1200 and turn.ttft_ms == 900
    assert turn.created_at.startswith("2026-09-26T12:00")
    assert await history.get_turn("missing") is None


async def test_lists_newest_first_with_total_and_paging(history: SqliteHistory) -> None:
    for i in range(5):
        await history.record(result(f"m{i}"))

    page, total = await history.list_turns(HistoryFilter(), limit=2, offset=0)
    assert total == 5
    assert [t.message_id for t in page] == ["m4", "m3"]
    page, _ = await history.list_turns(HistoryFilter(), limit=2, offset=4)
    assert [t.message_id for t in page] == ["m0"]


async def test_filters(history: SqliteHistory, clock: Clock) -> None:
    await history.record(result("a", "What is the SCIM rate limit?"))
    await history.record(result("b", "Price of Enterprise?", refused=True, provider=None))
    clock.now = NOW + timedelta(days=2)
    await history.record(result("c", "Webhook signature header?", provider="anthropic"))

    async def ids(**kwargs: object) -> list[str]:
        turns, _ = await history.list_turns(HistoryFilter(**kwargs), limit=50, offset=0)  # type: ignore[arg-type]
        return sorted(t.message_id for t in turns)

    assert await ids(text="scim") == ["a"]
    assert await ids(text="35 days") == ["a", "c"]  # matches the answer too
    assert await ids(refused=True) == ["b"]
    assert await ids(provider="anthropic") == ["c"]
    assert await ids(provider="none") == ["b"]
    assert await ids(date_from=date(2026, 9, 27)) == ["c"]
    assert await ids(date_to=date(2026, 9, 26)) == ["a", "b"]


async def test_like_wildcards_in_the_search_are_literal(history: SqliteHistory) -> None:
    await history.record(result("a", "Uptime was 98% last month"))
    await history.record(result("b", "Uptime was 98 last month"))
    turns, _ = await history.list_turns(HistoryFilter(text="98%"), limit=50, offset=0)
    assert [t.message_id for t in turns] == ["a"]


async def test_purges_turns_older_than_the_retention(tmp_path: Path, clock: Clock) -> None:
    path = tmp_path / "history.sqlite"
    store = SqliteHistory(path, retention_days=30, clock=clock)
    store.open()
    await store.record(result("old"))
    store.close()

    clock.now = NOW + timedelta(days=31)
    reopened = SqliteHistory(path, retention_days=30, clock=clock)
    reopened.open()  # purges on startup; reopening also re-runs the (already applied) migrations
    await reopened.record(result("new"))
    turns, total = await reopened.list_turns(HistoryFilter(), limit=50, offset=0)
    assert total == 1 and turns[0].message_id == "new"
    reopened.close()


async def test_a_storage_failure_does_not_break_the_chat(history: SqliteHistory) -> None:
    history.close()  # every write now fails
    await history.record(result("m1"))  # must not raise
