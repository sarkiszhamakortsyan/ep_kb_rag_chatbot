"""Retrieval benchmark with real embeddings. Run: uv run pytest -m eval -s

Needs Ollama; the first run embeds the KB (slow on CPU), later runs reuse data/index/.
"""

from collections.abc import AsyncIterator

import pytest

from app.core.config import Settings
from app.evaluation.dataset import load_questions
from app.evaluation.retrieval import evaluate_retrieval, format_report
from app.providers.embeddings.registry import build_embedding_registry
from app.rag.ingest import build_or_load_index
from app.rag.retrieval import Retriever

pytestmark = [pytest.mark.eval, pytest.mark.anyio]

OFF_TOPIC = [
    "What is the weather in Frankfurt today?",
    "Tell me a joke about cats.",
    "Who won the football world cup?",
]


@pytest.fixture
async def retriever() -> AsyncIterator[Retriever]:
    settings = Settings()
    registry = build_embedding_registry(settings)
    embedder = registry.get()
    store, _ = await build_or_load_index(
        settings.kb_dir, settings.index_dir, embedder, settings.chunking()
    )
    yield Retriever(embedder, store, top_k=settings.top_k, min_score=settings.min_score)
    await registry.aclose()


async def test_expected_documents_are_retrieved(retriever: Retriever) -> None:
    report = await evaluate_retrieval(retriever, load_questions(), k=retriever.top_k)
    print("\n" + format_report(report, retriever.min_score))
    assert report.mean_recall >= 0.8
    assert report.hit_rate >= 0.9
    # MIN_SCORE must never refuse a question the KB can answer.
    assert all(r.top_score >= retriever.min_score for r in report.answerable)


@pytest.mark.parametrize("question", OFF_TOPIC)
async def test_off_topic_questions_are_below_min_score(retriever: Retriever, question: str) -> None:
    result = await retriever.retrieve(question)
    assert not result.covered, f"{question!r} scored {result.top_score:.3f}"
