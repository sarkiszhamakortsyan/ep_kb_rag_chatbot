"""Admin authentication: a single shared token (ADMIN_TOKEN) sent as a Bearer token.

Hiding the admin page in the UI is not security; this check is. With no token configured the
admin area is switched off entirely (404), so a forgotten setting never exposes the history.
"""

import secrets
from typing import Annotated

from fastapi import Depends, Header

from app.api.errors import AdminDisabledError, UnauthorizedError
from app.core.config import Settings, get_settings


def require_admin(
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    if settings.admin_token is None:
        raise AdminDisabledError("The admin area is disabled. Set ADMIN_TOKEN to enable it.")
    scheme, _, token = (authorization or "").partition(" ")
    expected = settings.admin_token.get_secret_value()
    if scheme.lower() != "bearer" or not secrets.compare_digest(token.encode(), expected.encode()):
        raise UnauthorizedError("Missing or invalid admin token.")
