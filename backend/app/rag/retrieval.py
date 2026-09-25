import time
from dataclasses import dataclass

from app.providers.embeddings.base import EmbeddingProvider
from app.stores.vector.base import SearchResult, VectorStore


@dataclass(frozen=True)
class RetrievalResult:
    results: list[SearchResult]
    top_score: float
    # False when even the best match is below MIN_SCORE: the KB most likely has no answer,
    # so the pipeline can refuse without spending an LLM call.
    covered: bool
    embed_ms: float
    search_ms: float


class Retriever:
    def __init__(
        self, embedder: EmbeddingProvider, store: VectorStore, *, top_k: int, min_score: float
    ) -> None:
        self._embedder = embedder
        self._store = store
        self.top_k = top_k
        self.min_score = min_score

    async def retrieve(self, question: str, top_k: int | None = None) -> RetrievalResult:
        started = time.perf_counter()
        vector = await self._embedder.embed_query(question)
        embedded = time.perf_counter()
        results = self._store.search(vector, top_k or self.top_k)
        finished = time.perf_counter()
        top_score = results[0].score if results else -1.0
        return RetrievalResult(
            results=results,
            top_score=top_score,
            covered=top_score >= self.min_score,
            embed_ms=(embedded - started) * 1000,
            search_ms=(finished - embedded) * 1000,
        )
