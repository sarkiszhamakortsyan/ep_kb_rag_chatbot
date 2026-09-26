from dataclasses import asdict
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.api.errors import InvalidRangeError
from app.api.v1.admin.common import ADMIN_ERRORS, History

router = APIRouter()

MAX_RANGE_DAYS = 366


class DayCountOut(BaseModel):
    day: str
    answered: int
    refused: int


class ModelStatsOut(BaseModel):
    provider: str | None
    model: str | None
    questions: int
    refused: int
    p50_ms: float | None
    p95_ms: float | None
    ttft_p50_ms: float | None


class SourceCountOut(BaseModel):
    doc_id: str
    title: str
    section: str | None
    citations: int


class RefusedQuestionOut(BaseModel):
    created_at: str
    message_id: str
    question: str
    reason: str | None


class StatsOut(BaseModel):
    date_from: str
    date_to: str
    questions: int
    answered: int
    refused: int
    conversations: int
    refused_by_reason: dict[str, int]
    p50_ms: float | None
    per_day: list[DayCountOut]
    per_model: list[ModelStatsOut]
    top_documents: list[SourceCountOut]
    top_sections: list[SourceCountOut]
    recent_refused: list[RefusedQuestionOut]


@router.get("/stats", response_model=StatsOut, responses=ADMIN_ERRORS)
async def usage_stats(
    history: History,
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
) -> Any:
    """Usage statistics for a UTC date range (default: the last 30 days)."""
    to = date_to or datetime.now(UTC).date()
    start = date_from or to - timedelta(days=29)
    if start > to or (to - start).days >= MAX_RANGE_DAYS:
        raise InvalidRangeError(f"'from' must be before 'to', at most {MAX_RANGE_DAYS} days apart.")
    return asdict(await history.stats(start, to))
