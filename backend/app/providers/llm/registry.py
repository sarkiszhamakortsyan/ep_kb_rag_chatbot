from collections.abc import Callable, Mapping
from functools import partial

from app.core.config import Settings
from app.providers.llm.base import LLMProvider
from app.providers.registry import ProviderRegistry

LLMRegistry = ProviderRegistry[LLMProvider]


def _ollama(settings: Settings) -> LLMProvider:
    from app.providers.llm.ollama import OllamaLLMProvider

    return OllamaLLMProvider(
        settings.ollama_base_url,
        settings.ollama_chat_model,
        num_ctx=settings.ollama_num_ctx,
        keep_alive=settings.ollama_keep_alive,
        think=settings.ollama_think,
        timeout_s=settings.ollama_timeout_s,
    )


def _anthropic(settings: Settings) -> LLMProvider:
    from app.providers.llm.anthropic import AnthropicLLMProvider

    key = settings.anthropic_api_key
    return AnthropicLLMProvider(
        key.get_secret_value() if key else None,
        settings.anthropic_model,
        effort=settings.anthropic_effort,
        refusal_fallback=settings.anthropic_refusal_fallback,
    )


DEFAULT_FACTORIES: Mapping[str, Callable[[Settings], LLMProvider]] = {
    "ollama": _ollama,
    "anthropic": _anthropic,
}


def build_llm_registry(
    settings: Settings,
    factories: Mapping[str, Callable[[Settings], LLMProvider]] = DEFAULT_FACTORIES,
) -> LLMRegistry:
    return ProviderRegistry(
        {name: partial(factory, settings) for name, factory in factories.items()},
        enabled=settings.enabled_llm_providers,
        default=settings.llm_provider,
    )
