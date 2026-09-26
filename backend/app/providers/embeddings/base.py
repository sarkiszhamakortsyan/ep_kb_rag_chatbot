"""Embedding provider interface, kept separate from chat providers.

Anthropic has no embeddings API, so "Claude only" (ideas.md #7) needs a non-Ollama
implementation of this interface (in-process model or Voyage AI) rather than a new pipeline.
"""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass

Vector = list[float]


@dataclass(frozen=True)
class EmbeddingDocument:
    text: str
    title: str | None = None


class EmbeddingProvider(ABC):
    name: str
    model: str
    # Anything besides the model that changes document vectors (e.g. a prompt template).
    # Part of the index fingerprint, so changing it rebuilds the index.
    document_format: str = ""

    @abstractmethod
    async def embed_documents(self, documents: Sequence[EmbeddingDocument]) -> list[Vector]:
        """Embed KB chunks, returned in input order."""

    @abstractmethod
    async def embed_query(self, query: str) -> Vector:
        """Embed a user question (query and document embeddings may use different prompts)."""

    async def aclose(self) -> None:  # noqa: B027 - optional hook, no-op by default
        """Release network resources."""
