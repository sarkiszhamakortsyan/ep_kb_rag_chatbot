"""Deterministic in-memory providers for offline tests (reused by pipeline and API tests)."""

import hashlib
from collections.abc import AsyncIterator, Sequence

from app.providers.embeddings.base import EmbeddingDocument, EmbeddingProvider, Vector
from app.providers.llm.base import (
    ChatMessage,
    GenerationDone,
    GenerationOptions,
    LLMProvider,
    StreamEvent,
    TextDelta,
    Usage,
)


class FakeLLM(LLMProvider):
    """Streams a canned answer word by word and records every call."""

    def __init__(
        self, answer: str = "Fake answer [1].", name: str = "fake", model: str = "fake-1"
    ) -> None:
        self.name = name
        self.model = model
        self.answer = answer
        self.calls: list[tuple[str, list[ChatMessage]]] = []
        self.closed = False

    async def stream(
        self,
        system: str,
        messages: Sequence[ChatMessage],
        options: GenerationOptions | None = None,
    ) -> AsyncIterator[StreamEvent]:
        self.calls.append((system, list(messages)))
        words = self.answer.split(" ")
        for i, word in enumerate(words):
            yield TextDelta(word if i == 0 else f" {word}")
        yield GenerationDone(
            usage=Usage(input_tokens=len(system.split()), output_tokens=len(words)),
            stop_reason="end_turn",
            model=self.model,
        )

    async def aclose(self) -> None:
        self.closed = True


class FakeEmbedder(EmbeddingProvider):
    """Bag-of-words hashing embedder: texts sharing words get similar vectors."""

    def __init__(self, dimensions: int = 64, name: str = "fake", model: str = "fake-embed") -> None:
        self.name = name
        self.model = model
        self.dimensions = dimensions

    def _vector(self, text: str) -> Vector:
        vector = [0.0] * self.dimensions
        for word in text.lower().split():
            digest = hashlib.sha256(word.strip(".,?!:;()").encode()).digest()
            vector[int.from_bytes(digest[:4], "big") % self.dimensions] += 1.0
        return vector

    async def embed_documents(self, documents: Sequence[EmbeddingDocument]) -> list[Vector]:
        return [self._vector(d.text) for d in documents]

    async def embed_query(self, query: str) -> Vector:
        return self._vector(query)
