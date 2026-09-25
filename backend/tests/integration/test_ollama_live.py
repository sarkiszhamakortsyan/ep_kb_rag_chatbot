"""Checks against a real Ollama (docker compose up -d ollama). Run: uv run pytest -m integration"""

import math

import pytest

from app.core.config import Settings
from app.providers.embeddings.base import EmbeddingDocument
from app.providers.embeddings.registry import build_embedding_registry
from app.providers.llm.base import ChatMessage, GenerationOptions
from app.providers.llm.registry import build_llm_registry

pytestmark = [pytest.mark.integration, pytest.mark.anyio]


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    return dot / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))


async def test_embeddings_rank_related_text_higher() -> None:
    registry = build_embedding_registry(Settings())
    embedder = registry.get()
    try:
        docs = await embedder.embed_documents(
            [
                EmbeddingDocument("Backups are retained for 35 days.", "Backups"),
                EmbeddingDocument("Webhooks are signed with HMAC-SHA256.", "Webhooks"),
            ]
        )
        query = await embedder.embed_query("How long do you keep backups?")
    finally:
        await registry.aclose()
    assert len(query) == len(docs[0]) > 0
    assert cosine(query, docs[0]) > cosine(query, docs[1])


async def test_chat_model_generates() -> None:
    registry = build_llm_registry(Settings())
    llm = registry.get("ollama")
    try:
        result = await llm.generate(
            "Answer with one word.",
            [ChatMessage("user", "What colour is the sky on a clear day?")],
            GenerationOptions(max_output_tokens=5),
        )
    finally:
        await registry.aclose()
    assert result.text.strip()
    assert result.usage.output_tokens > 0
