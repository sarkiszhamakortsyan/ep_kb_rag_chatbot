from typing import Annotated

from fastapi import Depends, Request

from app.api.errors import HistoryDisabledError
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
