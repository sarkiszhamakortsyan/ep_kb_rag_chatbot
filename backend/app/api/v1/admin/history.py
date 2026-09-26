import csv
import io
from collections.abc import Iterator
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.api.errors import NotFoundError
from app.api.v1.admin.common import ADMIN_ERRORS, History
from app.stores.history.sqlite import HistoryFilter, Turn

router = APIRouter(prefix="/history")


class TurnSummary(BaseModel):
    created_at: str
    conversation_id: str
    message_id: str
    question: str
    refused: bool
    refusal_reason: str | None
    provider: str | None
    model: str | None
    sources: int  # cited sources
    total_ms: float


class TurnDetail(BaseModel):
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


class HistoryPage(BaseModel):
    items: list[TurnSummary]
    total: int
    limit: int
    offset: int


def history_filter(
    q: Annotated[
        str | None, Query(max_length=200, description="Text in question or answer")
    ] = None,
    provider: Annotated[
        str | None, Query(max_length=40, description="'ollama', 'anthropic' or 'none'")
    ] = None,
    refused: Annotated[bool | None, Query(description="true = not covered")] = None,
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
) -> HistoryFilter:
    return HistoryFilter(
        text=q or None,
        provider=provider or None,
        refused=refused,
        date_from=date_from,
        date_to=date_to,
    )


Filters = Annotated[HistoryFilter, Depends(history_filter)]


def _summary(t: Turn) -> TurnSummary:
    return TurnSummary(
        created_at=t.created_at,
        conversation_id=t.conversation_id,
        message_id=t.message_id,
        question=t.question,
        refused=t.refused,
        refusal_reason=t.refusal_reason,
        provider=t.provider,
        model=t.model,
        sources=len(t.citations),
        total_ms=t.total_ms,
    )


@router.get("", response_model=HistoryPage, responses=ADMIN_ERRORS)
async def list_history(
    history: History,
    filters: Filters,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> HistoryPage:
    """Stored chat turns, newest first."""
    turns, total = await history.list_turns(filters, limit=limit, offset=offset)
    return HistoryPage(items=[_summary(t) for t in turns], total=total, limit=limit, offset=offset)


CSV_COLUMNS = [
    "created_at", "conversation_id", "message_id", "question", "answer", "cited_documents",
    "refused", "refusal_reason", "provider", "model", "top_score", "input_tokens",
    "output_tokens", "cache_read_tokens", "ttft_ms", "total_ms",
]  # fmt: skip


@router.get(
    "/export.csv",
    response_class=StreamingResponse,
    responses={**ADMIN_ERRORS, 200: {"content": {"text/csv": {}}, "description": "CSV file"}},
)
def export_history(history: History, filters: Filters) -> StreamingResponse:
    """All matching turns as CSV (opens in Excel)."""

    def rows() -> Iterator[str]:
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        buffer.write("﻿")  # BOM, so Excel detects UTF-8
        writer.writerow(CSV_COLUMNS)
        for t in history.iter_turns(filters):
            docs = sorted({c["doc_id"] for c in t.citations})
            ttft = "" if t.ttft_ms is None else round(t.ttft_ms)
            writer.writerow(
                [
                    t.created_at,
                    t.conversation_id,
                    t.message_id,
                    _cell(t.question),
                    _cell(t.answer),
                    " ".join(docs),
                    t.refused,
                    t.refusal_reason or "",
                    t.provider or "",
                    t.model or "",
                    round(t.top_score, 4),
                    t.input_tokens,
                    t.output_tokens,
                    t.cache_read_tokens,
                    ttft,
                    round(t.total_ms),
                ]
            )
            yield buffer.getvalue()
            buffer.seek(0)
            buffer.truncate()
        yield buffer.getvalue()

    return StreamingResponse(
        rows(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="chat-history.csv"'},
    )


def _cell(text: str) -> str:
    # Spreadsheet apps run cells starting with these characters as formulas (CSV injection).
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


@router.get("/{message_id}", response_model=TurnDetail, responses=ADMIN_ERRORS)
async def get_history_turn(message_id: str, history: History) -> TurnDetail:
    """One turn with the full answer, its sources and all metrics."""
    turn = await history.get_turn(message_id)
    if turn is None:
        raise NotFoundError(f"No stored turn with message_id {message_id!r}.")
    return TurnDetail(**turn.__dict__)
