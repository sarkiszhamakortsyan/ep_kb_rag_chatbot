"""Application entry point. `create_app` wires the settings, the services, background index
loading, the SQLite response history, the v1 and admin routes, the MCP HTTP endpoint, the
error handlers and the request-id middleware; `api` is the instance that uvicorn serves."""

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import app
from app.api.errors import install_error_handlers
from app.api.middleware import RequestContextMiddleware
from app.api.state import AppState, get_services
from app.api.v1 import admin, chat, health, providers
from app.api.v1.admin.settings import apply_stored_policy
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.evaluation.runner import EvalRunner
from app.mcp.http import MOUNT_PATH, mcp_http_app
from app.mcp.server import build_mcp_server
from app.services import Services, create_services
from app.stores.events.base import EventStore
from app.stores.events.fanout import FanOutEventStore
from app.stores.events.log_only import LogOnlyEventStore
from app.stores.events.memory import InMemoryConversations
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

    # The MCP server (dev-features) shares the API's services; it exists only with MCP_TOKEN.
    mcp_server = (
        build_mcp_server(lambda: get_services(api.state.app_state)) if settings.mcp_token else None
    )

    @asynccontextmanager
    async def lifespan(api: FastAPI) -> AsyncIterator[None]:
        # The history opens before the index loads, so the admin area works while it builds.
        history = _open_history(settings)
        api.state.history = history
        eval_runner = EvalRunner(history.save_eval_run) if history else None
        api.state.eval_runner = eval_runner
        # The history (or, without it, a small in-memory store) also remembers recent turns
        # for follow-up questions.
        memory: EventStore = history or InMemoryConversations()
        events: EventStore = FanOutEventStore([LogOnlyEventStore(), memory])

        async def build() -> Services:
            services = await services_factory(settings, events)
            apply_stored_policy(services, history)  # the admin's last model choices
            return services

        state = AppState()
        api.state.app_state = state
        if load_in_background:
            state.start(build)
        else:
            await state.load(build)
        async with AsyncExitStack() as stack:
            if mcp_server:
                await stack.enter_async_context(mcp_server.session_manager.run())
            yield
        if eval_runner:
            await eval_runner.close()
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
    if mcp_server and settings.mcp_token:
        token = settings.mcp_token.get_secret_value()
        api.mount(MOUNT_PATH, mcp_http_app(mcp_server, token, settings.mcp_allowed_hosts))
    return api


def _app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    return create_app(settings)


api = _app()
