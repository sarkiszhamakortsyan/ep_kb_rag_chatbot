"""Response history in SQLite (ideas.md #5): one row per chat turn.

It implements the pipeline's `EventStore` hook for writing, and the queries the admin area
reads. SQLite needs no extra service: the file lives in a Docker volume. Calls run in a worker
thread (`asyncio.to_thread`) on one connection guarded by a lock, which is plenty for an
internal tool. Schema changes are numbered SQL files in `migrations/`, applied in order and
tracked with `PRAGMA user_version`.
"""

import asyncio
import json
import logging
import sqlite3
import threading
from collections.abc import Callable, Iterator
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.stores.events.base import EventStore
from app.stores.history.stats import UsageStats, compute_stats

if TYPE_CHECKING:
    from app.rag.pipeline import ChatResult

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
PURGE_INTERVAL = timedelta(hours=24)


@dataclass(frozen=True)
class HistoryFilter:
    text: str | None = None  # substring of the question or answer (case-insensitive)
    provider: str | None = None
    refused: bool | None = None
    date_from: date | None = None  # inclusive, UTC
    date_to: date | None = None  # inclusive, UTC


@dataclass(frozen=True)
class Turn:
    created_at: str
    conversation_id: str
    message_id: str
    question: str
    answer: str
    citations: list[dict[str, Any]]
    refused: bool
    refusal_reason: str | None
    provider: str | None
    model: str | None
    language: str | None
    stop_reason: str | None
    top_score: float
    sources_used: int
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_creation_tokens: int
    embed_ms: float
    search_ms: float
    ttft_ms: float | None
    generation_ms: float
    total_ms: float


def _now() -> datetime:
    return datetime.now(UTC)


class SqliteHistory(EventStore):
    def __init__(
        self, path: Path, retention_days: int, *, clock: Callable[[], datetime] = _now
    ) -> None:
        self.path = path
        self.retention_days = retention_days
        self._clock = clock
        self._lock = threading.Lock()
        self._conn: sqlite3.Connection | None = None
        self._last_purge: datetime | None = None

    # --- lifecycle ----------------------------------------------------------------------------

    def open(self) -> None:
        """Create the file if needed, apply migrations and drop expired turns."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        self._conn = conn
        self._migrate()
        self._purge()

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    def _migrate(self) -> None:
        with self._lock:
            conn = self._connection()
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            for script in sorted(MIGRATIONS_DIR.glob("*.sql")):
                number = int(script.name.split("_", 1)[0])
                if number <= version:
                    continue
                with conn:  # one transaction per migration
                    conn.executescript(script.read_text(encoding="utf-8"))
                    conn.execute(f"PRAGMA user_version = {number}")
                logger.info("History database migrated to version %d", number)

    def _connection(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("SqliteHistory.open() was not called")
        return self._conn

    # --- writing (EventStore hook) -----------------------------------------------------------

    async def record(self, result: "ChatResult") -> None:
        # A history failure must never break the chat: log it and carry on.
        try:
            await asyncio.to_thread(self._insert, result)
        except Exception:
            logger.exception("Could not store the chat turn in the history")

    def _insert(self, result: "ChatResult") -> None:
        now = self._clock()
        citations = [asdict(c) for c in result.citations]
        with self._lock:
            conn = self._connection()
            with conn:
                conn.execute(
                    """INSERT OR REPLACE INTO turns (
                        created_at, conversation_id, message_id, question, answer, citations,
                        refused, refusal_reason, provider, model, language, stop_reason,
                        top_score, sources_used, input_tokens, output_tokens,
                        cache_read_tokens, cache_creation_tokens,
                        embed_ms, search_ms, ttft_ms, generation_ms, total_ms
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        now.isoformat(timespec="milliseconds"),
                        result.conversation_id,
                        result.message_id,
                        result.question,
                        result.answer,
                        json.dumps(citations, ensure_ascii=False),
                        int(result.refused),
                        result.refusal_reason,
                        result.provider,
                        result.model,
                        result.language,
                        result.stop_reason,
                        result.top_score,
                        result.sources_used,
                        result.usage.input_tokens,
                        result.usage.output_tokens,
                        result.usage.cache_read_input_tokens,
                        result.usage.cache_creation_input_tokens,
                        result.timings.embed_ms,
                        result.timings.search_ms,
                        result.timings.time_to_first_token_ms,
                        result.timings.generation_ms,
                        result.timings.total_ms,
                    ),
                )
        if self._last_purge is None or now - self._last_purge > PURGE_INTERVAL:
            self._purge()

    def _purge(self) -> int:
        now = self._clock()
        cutoff = (now - timedelta(days=self.retention_days)).isoformat(timespec="milliseconds")
        with self._lock:
            conn = self._connection()
            with conn:
                deleted = conn.execute("DELETE FROM turns WHERE created_at < ?", (cutoff,)).rowcount
        self._last_purge = now
        if deleted:
            logger.info("Deleted %d turns older than %d days", deleted, self.retention_days)
        return deleted

    # --- reading (admin area) ----------------------------------------------------------------

    async def list_turns(
        self, filters: HistoryFilter, *, limit: int, offset: int
    ) -> tuple[list[Turn], int]:
        """Newest first, plus the total number of matching turns."""
        return await asyncio.to_thread(self._list, filters, limit, offset)

    async def get_turn(self, message_id: str) -> Turn | None:
        return await asyncio.to_thread(self._get, message_id)

    async def stats(self, date_from: date, date_to: date) -> UsageStats:
        """Usage statistics for the inclusive UTC date range."""
        return await asyncio.to_thread(self._stats, date_from, date_to)

    def _stats(self, date_from: date, date_to: date) -> UsageStats:
        with self._lock:
            return compute_stats(self._connection(), date_from, date_to)

    def iter_turns(self, filters: HistoryFilter) -> Iterator[Turn]:
        """All matching turns, newest first (for CSV export; runs in the caller's thread)."""
        where, params = _where(filters)
        with self._lock:
            rows = (
                self._connection()
                .execute(f"SELECT * FROM turns {where} ORDER BY id DESC", params)
                .fetchall()
            )
        for row in rows:
            yield _turn(row)

    def _list(self, filters: HistoryFilter, limit: int, offset: int) -> tuple[list[Turn], int]:
        where, params = _where(filters)
        with self._lock:
            conn = self._connection()
            total = conn.execute(f"SELECT COUNT(*) FROM turns {where}", params).fetchone()[0]
            rows = conn.execute(
                f"SELECT * FROM turns {where} ORDER BY id DESC LIMIT ? OFFSET ?",
                [*params, limit, offset],
            ).fetchall()
        return [_turn(r) for r in rows], total

    def _get(self, message_id: str) -> Turn | None:
        with self._lock:
            row = (
                self._connection()
                .execute("SELECT * FROM turns WHERE message_id = ?", (message_id,))
                .fetchone()
            )
        return _turn(row) if row else None


def _where(filters: HistoryFilter) -> tuple[str, list[Any]]:
    """WHERE clause built from fixed fragments; values always go through parameters."""
    clauses: list[str] = []
    params: list[Any] = []
    if filters.text:
        clauses.append("(question LIKE ? ESCAPE '\\' OR answer LIKE ? ESCAPE '\\')")
        pattern = "%" + _escape_like(filters.text) + "%"
        params += [pattern, pattern]
    if filters.provider == "none":  # refused before any LLM call
        clauses.append("provider IS NULL")
    elif filters.provider:
        clauses.append("provider = ?")
        params.append(filters.provider)
    if filters.refused is not None:
        clauses.append("refused = ?")
        params.append(int(filters.refused))
    if filters.date_from:
        clauses.append("created_at >= ?")
        params.append(filters.date_from.isoformat())
    if filters.date_to:
        clauses.append("created_at < ?")
        params.append((filters.date_to + timedelta(days=1)).isoformat())
    return ("WHERE " + " AND ".join(clauses) if clauses else ""), params


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _turn(row: sqlite3.Row) -> Turn:
    data = dict(row)
    data.pop("id")
    data["citations"] = json.loads(data["citations"])
    data["refused"] = bool(data["refused"])
    return Turn(**data)
