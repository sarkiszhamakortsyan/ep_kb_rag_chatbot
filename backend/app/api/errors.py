"""Maps domain errors to HTTP responses with one error body shape: {"error": {code, message}}."""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.providers.errors import (
    ProviderConfigError,
    ProviderDisabledError,
    ProviderError,
    ProviderUnavailableError,
    UnknownProviderError,
)

logger = logging.getLogger(__name__)


class ServiceNotReadyError(Exception):
    """The knowledge-base index is still loading (or failed to load)."""


class AdminDisabledError(Exception):
    """ADMIN_TOKEN is not set, so the admin area does not exist."""


class UnauthorizedError(Exception):
    """Missing or wrong admin token."""


class HistoryDisabledError(Exception):
    """HISTORY_ENABLED=false, so nothing is stored."""


class NotFoundError(Exception):
    """The requested record does not exist."""


def error_payload(exc: Exception) -> tuple[int, str, str]:
    """(status, code, message) for an exception. Shared by JSON responses and SSE error events."""
    if isinstance(exc, ServiceNotReadyError):
        return 503, "not_ready", str(exc)
    if isinstance(exc, AdminDisabledError):
        return 404, "admin_disabled", str(exc)
    if isinstance(exc, UnauthorizedError):
        return 401, "unauthorized", str(exc)
    if isinstance(exc, HistoryDisabledError):
        return 404, "history_disabled", str(exc)
    if isinstance(exc, NotFoundError):
        return 404, "not_found", str(exc)
    if isinstance(exc, UnknownProviderError | ProviderDisabledError):
        return 400, "invalid_provider", str(exc)
    if isinstance(exc, ProviderConfigError):
        return 503, "provider_not_configured", str(exc)
    if isinstance(exc, ProviderUnavailableError):
        return 503, "provider_unavailable", str(exc)
    if isinstance(exc, ProviderError):
        return 502, "provider_error", str(exc)
    return 500, "internal_error", "Internal server error"


def _response(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


def install_error_handlers(app: FastAPI) -> None:
    async def domain_error(request: Request, exc: Exception) -> JSONResponse:
        status, code, message = error_payload(exc)
        if status >= 500:
            logger.warning("%s: %s", code, exc)
        return _response(status, code, message)

    async def validation_error(request: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, RequestValidationError)
        first = exc.errors()[0] if exc.errors() else {}
        location = ".".join(str(p) for p in first.get("loc", ()) if p != "body")
        message = (
            f"{location}: {first.get('msg', 'invalid request')}" if location else "invalid request"
        )
        return _response(422, "validation_error", message)

    async def http_error(request: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, HTTPException)
        return _response(exc.status_code, "http_error", str(exc.detail))

    async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error")
        return _response(500, "internal_error", "Internal server error")

    for error in (
        ServiceNotReadyError,
        AdminDisabledError,
        UnauthorizedError,
        HistoryDisabledError,
        NotFoundError,
    ):
        app.add_exception_handler(error, domain_error)
    app.add_exception_handler(ProviderError, domain_error)
    app.add_exception_handler(RequestValidationError, validation_error)
    app.add_exception_handler(HTTPException, http_error)
    app.add_exception_handler(Exception, unexpected_error)
