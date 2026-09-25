from collections.abc import Callable, Mapping
from functools import partial

from app.core.config import Settings
from app.providers.embeddings.base import EmbeddingProvider
from app.providers.registry import ProviderRegistry

EmbeddingRegistry = ProviderRegistry[EmbeddingProvider]


def _ollama(settings: Settings) -> EmbeddingProvider:
    from app.providers.embeddings.ollama import OllamaEmbeddingProvider

    return OllamaEmbeddingProvider(
        settings.ollama_base_url,
        settings.ollama_embed_model,
        keep_alive=settings.ollama_keep_alive,
    )


DEFAULT_FACTORIES: Mapping[str, Callable[[Settings], EmbeddingProvider]] = {"ollama": _ollama}


def build_embedding_registry(
    settings: Settings,
    factories: Mapping[str, Callable[[Settings], EmbeddingProvider]] = DEFAULT_FACTORIES,
) -> EmbeddingRegistry:
    # Exactly one embedding provider is active: the vector index is tied to its model.
    return ProviderRegistry(
        {name: partial(factory, settings) for name, factory in factories.items()},
        enabled=[settings.embedding_provider],
        default=settings.embedding_provider,
    )
