"""Holds the services built at startup. The index can take minutes to build on a slow CPU,
so it loads in the background: the API is up immediately and reports `not_ready` until then."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Annotated

from fastapi import Depends, Request

from app.api.errors import ServiceNotReadyError
from app.providers.errors import ProviderUnavailableError
from app.services import Services

logger = logging.getLogger(__name__)

RETRY_DELAY_S = 15.0


@dataclass
class AppState:
    services: Services | None = None
    error: str | None = None
    failed: bool = False  # a non-retryable startup error; needs a config fix and restart
    _task: asyncio.Task[None] | None = field(default=None, repr=False)

    async def load(self, factory: Callable[[], Awaitable[Services]]) -> None:
        """Build the services. Temporary failures (e.g. Ollama still starting) are retried;
        configuration errors (unknown provider, missing KB...) are reported and not retried."""
        while self.services is None:
            try:
                self.services = await factory()
                self.error = None
                logger.info(
                    "Knowledge base ready: %d chunks (%s)",
                    self.services.index.chunks,
                    "rebuilt" if self.services.index.rebuilt else "from cache",
                )
            except ProviderUnavailableError as exc:
                self.error = f"{type(exc).__name__}: {exc}"
                logger.warning("Loading the knowledge base failed (%s); retrying", self.error)
                await asyncio.sleep(RETRY_DELAY_S)
            except Exception as exc:
                self.error = f"{type(exc).__name__}: {exc}"
                self.failed = True
                logger.error("Loading the knowledge base failed permanently: %s", self.error)
                return

    def start(self, factory: Callable[[], Awaitable[Services]]) -> None:
        self._task = asyncio.create_task(self.load(factory))

    async def close(self) -> None:
        if self._task is not None and not self._task.done():
            self._task.cancel()
        if self.services is not None:
            await self.services.aclose()


def get_state(request: Request) -> AppState:
    state: AppState = request.app.state.app_state
    return state


def get_services(state: Annotated[AppState, Depends(get_state)]) -> Services:
    if state.services is None:
        if state.failed:
            raise ServiceNotReadyError(f"The knowledge base failed to load: {state.error}")
        detail = f" Last error: {state.error}" if state.error else ""
        raise ServiceNotReadyError(f"The knowledge base is still loading.{detail}")
    return state.services
