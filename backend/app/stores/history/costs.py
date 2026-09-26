"""Cost report over the stored turns (ideas.md #2): totals, per day and model, a what-if
comparison with other Claude models, and rule-based optimisation hints from the real numbers."""

import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta

from app.core.pricing import DEFAULT_PRICES, PriceTable, TokenCounts, token_cost


@dataclass(frozen=True)
class DayCost:
    day: str
    usd: float


@dataclass
class ModelCost:
    provider: str | None
    model: str | None
    questions: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    usd: float = 0.0
    priced: bool = True  # False: a cloud model without a price (see MODEL_PRICES)


@dataclass(frozen=True)
class WhatIf:
    model: str
    usd: float  # the same Claude turns, priced as this model


@dataclass(frozen=True)
class Hint:
    kind: str  # "saving" (money to save) or "info"
    title: str
    detail: str


@dataclass
class CostReport:
    date_from: str
    date_to: str
    questions: int
    total_usd: float
    usd_per_question: float | None
    cache_savings_usd: float
    cache_share: float | None  # share of Claude input tokens served from the cache
    per_day: list[DayCost]
    per_model: list[ModelCost]
    what_if: list[WhatIf]
    hints: list[Hint] = field(default_factory=list)


def compute_costs(
    conn: sqlite3.Connection, date_from: date, date_to: date, prices: PriceTable, *, top_k: int
) -> CostReport:
    rows = conn.execute(
        """SELECT substr(created_at, 1, 10), provider, model, question, refusal_reason,
                  input_tokens, output_tokens, cache_read_tokens, cache_creation_tokens,
                  generation_ms
           FROM turns WHERE created_at >= ? AND created_at < ? ORDER BY id""",
        [date_from.isoformat(), (date_to + timedelta(days=1)).isoformat()],
    ).fetchall()

    per_day: dict[str, float] = defaultdict(float)
    models: dict[tuple[str | None, str | None], ModelCost] = {}
    claude_tokens: list[TokenCounts] = []
    savings = 0.0
    early_refusals = 0
    seen_questions: set[str] = set()
    repeat_usd, repeats = 0.0, 0

    for day, provider, model, question, reason, tin, tout, tread, twrite, gen_ms in rows:
        tokens = TokenCounts(tin, tout, tread, twrite)
        usd = prices.cost(provider, model, tokens, gen_ms)
        entry = models.setdefault((provider, model), ModelCost(provider, model))
        entry.questions += 1
        entry.input_tokens += tin
        entry.output_tokens += tout
        entry.cache_read_tokens += tread
        entry.cache_write_tokens += twrite
        if usd is None:
            entry.priced = False
            usd = 0.0
        entry.usd += usd
        per_day[day] += usd
        if reason == "low_score":
            early_refusals += 1
        if provider not in (None, "ollama"):
            claude_tokens.append(tokens)
            price = prices.price_for(model)
            if price:
                savings += tread * (price.input - price.cache_read) / 1_000_000
            key = " ".join(question.lower().split())
            if key in seen_questions:
                repeats += 1
                repeat_usd += usd
            seen_questions.add(key)

    total = sum(m.usd for m in models.values())
    questions = len(rows)
    claude_input = sum(t.input + t.cache_read + t.cache_write for t in claude_tokens)
    cache_share = sum(t.cache_read for t in claude_tokens) / claude_input if claude_input else None
    what_if = [
        WhatIf(name, sum(token_cost(price, t) for t in claude_tokens))
        for name, price in DEFAULT_PRICES.items()
    ]

    days = []
    day = date_from
    while day <= date_to:
        days.append(DayCost(day.isoformat(), round(per_day.get(day.isoformat(), 0.0), 6)))
        day += timedelta(days=1)

    report = CostReport(
        date_from=date_from.isoformat(),
        date_to=date_to.isoformat(),
        questions=questions,
        total_usd=total,
        usd_per_question=total / questions if questions else None,
        cache_savings_usd=savings,
        cache_share=cache_share,
        per_day=days,
        per_model=sorted(models.values(), key=lambda m: (-m.usd, -m.questions)),
        what_if=what_if,
    )
    report.hints = _hints(report, models, claude_tokens, early_refusals, repeats, repeat_usd, top_k)
    return report


def _hints(
    report: CostReport,
    models: dict[tuple[str | None, str | None], ModelCost],
    claude_tokens: list[TokenCounts],
    early_refusals: int,
    repeats: int,
    repeat_usd: float,
    top_k: int,
) -> list[Hint]:
    hints: list[Hint] = []
    claude_usd = sum(m.usd for (p, _), m in models.items() if p not in (None, "ollama"))

    cheapest = min(report.what_if, key=lambda w: w.usd, default=None)
    if claude_tokens and cheapest and cheapest.usd < claude_usd * 0.9:
        hints.append(
            Hint(
                "saving",
                f"A smaller Claude model would cost {_pct(1 - cheapest.usd / claude_usd)} less",
                f"The same {_n(len(claude_tokens), 'Claude question')} would have cost "
                f"{_usd(cheapest.usd)} with {cheapest.model} instead of {_usd(claude_usd)}. "
                "Run the answer benchmark with that model before switching (ANTHROPIC_MODEL): "
                "cheaper models can miss details or refusals.",
            )
        )
    if repeats:
        hints.append(
            Hint(
                "saving",
                f"{_n(repeats, 'repeated question')}",
                f"{_n(repeats, 'Claude question')} repeated an earlier one word for word and cost "
                f"{_usd(repeat_usd)}. An answer cache (reusing the vector store on past "
                "questions) would make repeats free and instant.",
            )
        )
    if claude_tokens:
        avg_input = sum(t.input + t.cache_read + t.cache_write for t in claude_tokens) / len(
            claude_tokens
        )
        hints.append(
            Hint(
                "info",
                f"About {round(avg_input):,} input tokens per Claude question",
                f"Most of the prompt is the {top_k} retrieved sections (TOP_K={top_k}). A lower "
                "TOP_K cuts input cost roughly in proportion, but check the benchmark: "
                "questions that need two documents rely on the extra sections.",
            )
        )
        if report.cache_share is not None:
            hints.append(
                Hint(
                    "info",
                    f"Prompt cache: {_pct(report.cache_share)} of Claude input tokens",
                    "Cached reads cost 10% of the input price and saved "
                    f"{_usd(report.cache_savings_usd)}. Only the fixed system prompt can be "
                    "cached; the retrieved sections differ per question.",
                )
            )
    if early_refusals:
        hints.append(
            Hint(
                "info",
                f"{_n(early_refusals, 'question')} refused at no cost",
                "Off-topic questions are refused by the similarity threshold (MIN_SCORE) before "
                "any model is called.",
            )
        )
    local = sum(m.questions for (p, _), m in models.items() if p == "ollama")
    if local:
        hints.append(
            Hint(
                "info",
                f"{_n(local, 'question')} answered by the local model",
                "They have no API cost. Set LOCAL_COST_PER_HOUR to include the hardware cost.",
            )
        )
    if any(not m.priced for m in models.values()):
        hints.append(
            Hint(
                "info",
                "Some models have no price",
                "Their cost is counted as $0. Add them to MODEL_PRICES.",
            )
        )
    return hints


def _n(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def _usd(value: float) -> str:
    return f"${value:.4f}" if value < 1 else f"${value:,.2f}"


def _pct(value: float) -> str:
    return f"{round(value * 100)}%"
