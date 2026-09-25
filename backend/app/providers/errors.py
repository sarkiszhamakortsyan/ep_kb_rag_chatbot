"""Provider-independent errors. The API layer maps these to HTTP status codes."""


class ProviderError(Exception):
    """A provider failed in a way that retrying will not fix (bad request, unknown model...)."""


class ProviderUnavailableError(ProviderError):
    """The provider is unreachable, overloaded or rate-limited; retrying later may succeed."""


class ProviderConfigError(ProviderError):
    """The provider is misconfigured, e.g. a missing or invalid API key."""


class ProviderDisabledError(ProviderError):
    """The provider exists but is not listed in ENABLED_LLM_PROVIDERS."""


class UnknownProviderError(ProviderError):
    """No provider with this name is registered."""
