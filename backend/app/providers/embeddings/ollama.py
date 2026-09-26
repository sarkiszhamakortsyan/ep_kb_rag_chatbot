from collections.abc import Sequence

import httpx

from app.providers.embeddings.base import EmbeddingDocument, EmbeddingProvider, Vector
from app.providers.errors import ProviderError, ProviderUnavailableError

_TIMEOUT = httpx.Timeout(connect=5.0, read=300.0, write=30.0, pool=5.0)

# Retrieval models are trained with task prefixes; omitting them hurts ranking.
# Keys are matched against the start of the model name. Documents use {title} and {text}.
_PROMPTS: dict[str, tuple[str, str]] = {
    "embeddinggemma": ("task: search result | query: {text}", "title: {title} | text: {text}"),
    "nomic-embed-text": ("search_query: {text}", "search_document: {text}"),
}
_PLAIN = ("{text}", "{text}")


class OllamaEmbeddingProvider(EmbeddingProvider):
    """Embeds text with Ollama's batch endpoint `/api/embed`."""

    name = "ollama"

    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        batch_size: int = 16,
        keep_alive: str = "30m",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.model = model
        self._batch_size = batch_size
        self._keep_alive = keep_alive
        self._query_prompt, self._document_prompt = next(
            (p for prefix, p in _PROMPTS.items() if model.startswith(prefix)), _PLAIN
        )
        self.document_format = self._document_prompt
        self._client = client or httpx.AsyncClient(base_url=base_url, timeout=_TIMEOUT)

    async def embed_documents(self, documents: Sequence[EmbeddingDocument]) -> list[Vector]:
        texts = [
            self._document_prompt.format(title=d.title or "none", text=d.text) for d in documents
        ]
        vectors: list[Vector] = []
        for start in range(0, len(texts), self._batch_size):
            vectors.extend(await self._embed(texts[start : start + self._batch_size]))
        return vectors

    async def embed_query(self, query: str) -> Vector:
        return (await self._embed([self._query_prompt.format(text=query)]))[0]

    async def _embed(self, texts: list[str]) -> list[Vector]:
        payload = {"model": self.model, "input": texts, "keep_alive": self._keep_alive}
        try:
            response = await self._client.post("/api/embed", json=payload)
        except httpx.TransportError as exc:
            raise ProviderUnavailableError(f"Ollama is unreachable: {exc}") from exc
        if response.status_code >= 400:
            message = f"Ollama embed returned HTTP {response.status_code}: {response.text}"
            error = ProviderUnavailableError if response.status_code >= 500 else ProviderError
            raise error(message)
        embeddings: list[Vector] = response.json().get("embeddings", [])
        if len(embeddings) != len(texts):
            raise ProviderError(f"Ollama returned {len(embeddings)} embeddings for {len(texts)}")
        return embeddings

    async def aclose(self) -> None:
        await self._client.aclose()
