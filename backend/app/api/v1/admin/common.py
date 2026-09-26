from datetime import UTC, date, datetime, timedelta
from typing import Annotated

from fastapi import Depends, Query, Request

from app.api.errors import HistoryDisabledError, InvalidRangeError
from app.api.schemas import ErrorResponse
from app.stores.history.sqlite import SqliteHistory

ADMIN_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"model": ErrorResponse, "description": "Missing or invalid admin token"},
    404: {"model": ErrorResponse, "description": "Admin area or history disabled, or not found"},
}


def get_history(request: Request) -> SqliteHistory:
    history: SqliteHistory | None = request.app.state.history
    if history is None:
        raise HistoryDisabledError("The response history is disabled (HISTORY_ENABLED=false).")
    return history


History = Annotated[SqliteHistory, Depends(get_history)]


MAX_RANGE_DAYS = 366


def date_range(
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
) -> tuple[date, date]:
    """Inclusive UTC date range; defaults to the last 30 days."""
    to = date_to or datetime.now(UTC).date()
    start = date_from or to - timedelta(days=29)
    if start > to or (to - start).days >= MAX_RANGE_DAYS:
        raise InvalidRangeError(f"'from' must be before 'to', at most {MAX_RANGE_DAYS} days apart.")
    return start, to


DateRange = Annotated[tuple[date, date], Depends(date_range)]
