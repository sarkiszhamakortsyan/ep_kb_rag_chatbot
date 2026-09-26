"""Admin API (`/api/v1/admin/*`): every route requires the ADMIN_TOKEN bearer token."""

from fastapi import APIRouter, Depends

from app.api.v1.admin import costs, history, session, stats
from app.core.security import require_admin

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])
router.include_router(session.router)
router.include_router(history.router)
router.include_router(stats.router)
router.include_router(costs.router)
