"""Usage statistics over the stored turns (ideas.md #1). Everything is computed from the `turns`
table on request; at prototype scale (thousands of rows) that takes milliseconds, so there are
no pre-aggregated tables to keep in sync."""

import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

from app.evaluation.stats import percentile


@dataclass(frozen=True)
class DayCount:
    day: str  # YYYY-MM-DD (UTC)
    answered: int
    refused: int


@dataclass(frozen=True)
class ModelStats:
    provider: str | None  # None: refused before any model was called
    model: str | None
    questions: int
    refused: int
    p50_ms: float | None
    p95_ms: float | None
    ttft_p50_ms: float | None


@dataclass(frozen=True)
class SourceCount:
    doc_id: str
    title: str
    section: str | None  # None when counting whole documents
    citations: int


@dataclass(frozen=True)
class RefusedQuestion:
    created_at: str
    message_id: str
    question: str
    reason: str | None


@dataclass(frozen=True)
class UsageStats:
    date_from: str
    date_to: str
    questions: int
    answered: int
    refused: int
    conversations: int
    refused_by_reason: dict[str, int]
    p50_ms: float | None
    per_day: list[DayCount]
    per_model: list[ModelStats]
    top_documents: list[SourceCount]
    top_sections: list[SourceCount]
    recent_refused: list[RefusedQuestion]


def compute_stats(conn: sqlite3.Connection, date_from: date, date_to: date) -> UsageStats:
    where = "created_at >= ? AND created_at < ?"
    params = [date_from.isoformat(), (date_to + timedelta(days=1)).isoformat()]

    totals = conn.execute(
        f"""SELECT COUNT(*), COALESCE(SUM(refused), 0), COUNT(DISTINCT conversation_id)
            FROM turns WHERE {where}""",
        params,
    ).fetchone()
    questions, refused, conversations = int(totals[0]), int(totals[1]), int(totals[2])

    reasons = dict(
        conn.execute(
            f"""SELECT refusal_reason, COUNT(*) FROM turns
                WHERE {where} AND refused = 1 GROUP BY refusal_reason""",
            params,
        ).fetchall()
    )

    per_day_rows = {
        row[0]: (int(row[1]), int(row[2]))
        for row in conn.execute(
            f"""SELECT substr(created_at, 1, 10), SUM(1 - refused), SUM(refused)
                FROM turns WHERE {where} GROUP BY 1""",
            params,
        )
    }
    per_day = []
    day = date_from
    while day <= date_to:  # every day in the range, including days without questions
        answered_n, refused_n = per_day_rows.get(day.isoformat(), (0, 0))
        per_day.append(DayCount(day.isoformat(), answered_n, refused_n))
        day += timedelta(days=1)

    times: dict[tuple[str | None, str | None], list[tuple[float, float | None, int]]] = defaultdict(
        list
    )
    for provider, model, total_ms, ttft_ms, was_refused in conn.execute(
        f"SELECT provider, model, total_ms, ttft_ms, refused FROM turns WHERE {where}", params
    ):
        times[(provider, model)].append((total_ms, ttft_ms, was_refused))
    per_model = sorted(
        (
            ModelStats(
                provider=provider,
                model=model,
                questions=len(rows),
                refused=sum(r[2] for r in rows),
                p50_ms=percentile((r[0] for r in rows), 50),
                p95_ms=percentile((r[0] for r in rows), 95),
                ttft_p50_ms=percentile((r[1] for r in rows if r[1] is not None), 50),
            )
            for (provider, model), rows in times.items()
        ),
        key=lambda m: -m.questions,
    )

    cited = f"""FROM turns, json_each(turns.citations) AS c WHERE {where}"""
    top_documents = [
        SourceCount(doc_id, title, None, int(n))
        for doc_id, title, n in conn.execute(
            f"""SELECT json_extract(c.value, '$.doc_id'), MAX(json_extract(c.value, '$.title')),
                       COUNT(*) {cited} GROUP BY 1 ORDER BY 3 DESC, 1 LIMIT 10""",
            params,
        )
    ]
    top_sections = [
        SourceCount(doc_id, title, section, int(n))
        for doc_id, title, section, n in conn.execute(
            f"""SELECT json_extract(c.value, '$.doc_id'), MAX(json_extract(c.value, '$.title')),
                       json_extract(c.value, '$.section'), COUNT(*) {cited}
                GROUP BY 1, 3 ORDER BY 4 DESC, 1, 3 LIMIT 10""",
            params,
        )
    ]

    recent_refused = [
        RefusedQuestion(*row)
        for row in conn.execute(
            f"""SELECT created_at, message_id, question, refusal_reason FROM turns
                WHERE {where} AND refused = 1 ORDER BY id DESC LIMIT 10""",
            params,
        )
    ]

    all_times = [r[0] for rows in times.values() for r in rows]
    return UsageStats(
        date_from=date_from.isoformat(),
        date_to=date_to.isoformat(),
        questions=questions,
        answered=questions - refused,
        refused=refused,
        conversations=conversations,
        refused_by_reason={str(k): int(v) for k, v in reasons.items()},
        p50_ms=percentile(all_times, 50),
        per_day=per_day,
        per_model=per_model,
        top_documents=top_documents,
        top_sections=top_sections,
        recent_refused=recent_refused,
    )
