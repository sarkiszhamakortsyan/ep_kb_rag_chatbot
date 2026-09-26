import dataclasses
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


async def test_usage_stats(history: SqliteHistory, clock: Clock) -> None:
    await history.record(result("a"))
    await history.record(result("b", provider="anthropic"))
    await history.record(result("c", "Price?", refused=True, provider=None))
    clock.now = NOW + timedelta(days=2)
    await history.record(result("d"))
    clock.now = NOW + timedelta(days=40)  # outside the range below
    await history.record(result("e"))

    stats = await history.stats(date(2026, 9, 25), date(2026, 9, 28))

    assert (stats.questions, stats.answered, stats.refused) == (4, 3, 1)
    assert stats.conversations == 1
    assert stats.refused_by_reason == {"no_citations": 1}
    assert [(d.day, d.answered, d.refused) for d in stats.per_day] == [
        ("2026-09-25", 0, 0),
        ("2026-09-26", 2, 1),
        ("2026-09-27", 0, 0),
        ("2026-09-28", 1, 0),
    ]
    by_provider = {m.provider: m for m in stats.per_model}
    assert by_provider["ollama"].questions == 2 and by_provider["ollama"].p50_ms == 1500
    assert by_provider[None].refused == 1
    assert stats.per_model[0].provider == "ollama"  # most questions first
    assert [(s.doc_id, s.citations) for s in stats.top_documents] == [("kb-003", 3)]
    assert stats.top_sections[0].section == "Backups"
    assert [q.message_id for q in stats.recent_refused] == ["c"]


async def test_usage_stats_on_an_empty_history(history: SqliteHistory) -> None:
    stats = await history.stats(date(2026, 9, 26), date(2026, 9, 26))
    assert stats.questions == 0 and stats.p50_ms is None
    assert stats.top_documents == [] and len(stats.per_day) == 1


async def test_cost_report(history: SqliteHistory) -> None:
    from app.core.pricing import PriceTable

    opus = result("a", "Question one", provider="anthropic")
    await history.record(dataclasses.replace(opus, model="claude-opus-5"))
    await history.record(dataclasses.replace(opus, message_id="b", model="claude-opus-5"))  # repeat
    await history.record(result("c"))  # local model
    await history.record(result("d", "Weather?", refused=True, provider=None))
    low = dataclasses.replace(
        result("e", "Cake?", refused=True, provider=None), refusal_reason="low_score"
    )
    await history.record(low)

    report = await history.costs(date(2026, 9, 26), date(2026, 9, 26), PriceTable(), top_k=6)

    # Each Claude turn: 1200 x $5 + 60 x $25 + 10 x $0.50 per million = $0.007505
    assert report.questions == 5
    assert report.total_usd == pytest.approx(2 * 0.007505)
    assert report.usd_per_question == pytest.approx(2 * 0.007505 / 5)
    assert report.per_day[0].usd == pytest.approx(0.01501)
    assert report.per_model[0].model == "claude-opus-5" and report.per_model[0].questions == 2
    assert report.cache_share == pytest.approx(10 / 1210)
    assert report.cache_savings_usd == pytest.approx(2 * 10 * 4.5 / 1_000_000)
    haiku = next(w for w in report.what_if if w.model == "claude-haiku-4-5")
    assert haiku.usd == pytest.approx(report.total_usd / 5)
    titles = " | ".join(h.title for h in report.hints)
    assert "smaller Claude model would cost 80% less" in titles
    assert "1 repeated question" in titles
    assert "1 question refused at no cost" in titles
    assert "1 question answered by the local model" in titles
