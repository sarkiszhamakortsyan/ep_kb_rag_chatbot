"""Name -> provider lookup driven by configuration (ideas.md #7: enable/disable models).

Providers are created lazily on first use, so the app starts even when an optional
provider is misconfigured (e.g. no Anthropic key while running Ollama only).
"""

from collections.abc import Callable, Iterable, Mapping
from typing import Protocol

from app.providers.errors import ProviderDisabledError, UnknownProviderError


class _Closable(Protocol):
    async def aclose(self) -> None: ...


class ProviderRegistry[P: _Closable]:
    def __init__(
        self,
        factories: Mapping[str, Callable[[], P]],
        enabled: Iterable[str],
        default: str,
    ) -> None:
        self._factories = dict(factories)
        self._enabled = list(enabled)
        self._instances: dict[str, P] = {}
        for name in self._enabled:
            if name not in self._factories:
                raise UnknownProviderError(f"Unknown provider {name!r}")
        self.default = default
        self._check_enabled(default)

    @property
    def enabled(self) -> list[str]:
        return list(self._enabled)

    def get(self, name: str | None = None) -> P:
        """Return the named (or default) provider; raises if it is unknown or disabled."""
        name = name or self.default
        self._check_enabled(name)
        if name not in self._instances:
            self._instances[name] = self._factories[name]()
        return self._instances[name]

    def _check_enabled(self, name: str) -> None:
        if name not in self._factories:
            raise UnknownProviderError(f"Unknown provider {name!r}")
        if name not in self._enabled:
            raise ProviderDisabledError(f"Provider {name!r} is disabled")

    async def aclose(self) -> None:
        for provider in self._instances.values():
            await provider.aclose()
        self._instances.clear()
