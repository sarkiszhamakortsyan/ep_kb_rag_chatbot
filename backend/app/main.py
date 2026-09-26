from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import app
from app.api.errors import install_error_handlers
from app.api.middleware import RequestContextMiddleware
from app.api.state import AppState
from app.api.v1 import admin, chat, health, providers
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.services import Services, create_services
from app.stores.events.base import EventStore
from app.stores.events.fanout import FanOutEventStore
from app.stores.events.log_only import LogOnlyEventStore
from app.stores.history.sqlite import SqliteHistory

# Builds the services; `events` receives every chat turn (log + history).
ServicesFactory = Callable[[Settings, EventStore], Awaitable[Services]]


def _open_history(settings: Settings) -> SqliteHistory | None:
    if not settings.history_enabled:
        return None
    history = SqliteHistory(settings.database_path, settings.history_retention_days)
    history.open()
    return history


def create_app(
    settings: Settings | None = None,
    services_factory: ServicesFactory = create_services,
    *,
    load_in_background: bool = True,
) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(api: FastAPI) -> AsyncIterator[None]:
        # The history opens before the index loads, so the admin area works while it builds.
        history = _open_history(settings)
        api.state.history = history
        events: EventStore = (
            FanOutEventStore([LogOnlyEventStore(), history]) if history else LogOnlyEventStore()
        )
        state = AppState()
        api.state.app_state = state
        if load_in_background:
            state.start(lambda: services_factory(settings, events))
        else:
            await state.load(lambda: services_factory(settings, events))
        yield
        await state.close()
        if history:
            history.close()

    api = FastAPI(
        title="OmniCorp Knowledge Base Assistant",
        version=app.__version__,
        description=(
            "RAG chatbot that answers questions strictly from OmniCorp's internal documentation "
            "and cites its sources."
        ),
        lifespan=lifespan,
    )
    api.dependency_overrides[get_settings] = lambda: settings
    api.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-Request-ID", "Authorization"],
        expose_headers=["X-Request-ID"],
    )

    api.add_middleware(RequestContextMiddleware)
    install_error_handlers(api)
    for router in (health.router, providers.router, chat.router, admin.router):
        api.include_router(router, prefix="/api/v1")
    return api


def _app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    return create_app(settings)


api = _app()
