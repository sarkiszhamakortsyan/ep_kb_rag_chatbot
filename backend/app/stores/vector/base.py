"""Vector store interface. The in-memory store is the prototype implementation; pgvector
or Chroma can implement the same interface when the corpus or deployment outgrows it."""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass

from app.rag.models import Chunk


@dataclass(frozen=True)
class SearchResult:
    chunk: Chunk
    score: float  # cosine similarity, -1..1


class VectorStore(ABC):
    @abstractmethod
    def add(self, chunks: Sequence[Chunk], vectors: Sequence[Sequence[float]]) -> None:
        """Add chunks with their embeddings (same order, same length)."""

    @abstractmethod
    def search(self, vector: Sequence[float], k: int) -> list[SearchResult]:
        """Return up to `k` chunks, most similar first."""

    @abstractmethod
    def count(self) -> int:
        """Number of stored chunks."""
