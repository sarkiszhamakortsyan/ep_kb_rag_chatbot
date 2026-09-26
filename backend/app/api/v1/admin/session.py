from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from app.api.v1.admin.common import ADMIN_ERRORS
from app.core.config import Settings, get_settings

router = APIRouter()


class AdminSession(BaseModel):
    history_enabled: bool
    history_retention_days: int


@router.get("/session", response_model=AdminSession, responses=ADMIN_ERRORS)
def session(request: Request, settings: Annotated[Settings, Depends(get_settings)]) -> AdminSession:
    """Checks the token (used by the admin login) and reports what the admin area offers."""
    return AdminSession(
        history_enabled=request.app.state.history is not None,
        history_retention_days=settings.history_retention_days,
    )
