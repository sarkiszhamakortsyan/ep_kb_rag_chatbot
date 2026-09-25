import logging
from collections.abc import AsyncIterator, Sequence
from functools import partial

import pytest

from app.providers.embeddings.base import EmbeddingDocument
from app.providers.errors import ProviderDisabledError
from app.providers.llm.base import (
    ChatMessage,
    GenerationDone,
    GenerationOptions,
    StreamEvent,
    Usage,
)
from app.providers.registry import ProviderRegistry
from app.rag.models import Chunk
from app.rag.pipeline import (
    AnswerDelta,
    ChatOptions,
    ChatResult,
    Completed,
    RagPipeline,
    SourcesEvent,
)
from app.rag.retrieval import Retriever
from app.stores.events.base import EventStore
from app.stores.events.log_only import LogOnlyEventStore
from app.stores.vector.memory import InMemoryVectorStore
from tests.fakes import FakeEmbedder, FakeLLM

pytestmark = pytest.mark.anyio

CHUNKS = [
    Chunk("kb-3#000", "kb-3", "Retention Policy", "Backups", "Backups are retained for 35 days."),
    Chunk(
        "kb-4#000", "kb-4", "Webhooks Manual", "Signing", "Webhooks are signed with HMAC-SHA256."
    ),
]


class RecordingEvents(EventStore):
    def __init__(self) -> None:
        self.results: list[ChatResult] = []

    async def record(self, result: ChatResult) -> None:
        self.results.append(result)


class RefusingLLM(FakeLLM):
    async def stream(
        self,
        system: str,
        messages: Sequence[ChatMessage],
        options: GenerationOptions | None = None,
    ) -> AsyncIterator[StreamEvent]:
        yield GenerationDone(usage=Usage(input_tokens=10), stop_reason="refusal", model="m")


async def make_pipeline(
    llms: dict[str, FakeLLM], enabled: list[str] | None = None, min_score: float = 0.4
) -> tuple[RagPipeline, RecordingEvents]:
    embedder = FakeEmbedder()
    store = InMemoryVectorStore()
    vectors = await embedder.embed_documents(
        [EmbeddingDocument(c.embedding_text(), c.title) for c in CHUNKS]
    )
    store.add(CHUNKS, vectors)
    registry = ProviderRegistry(
        {name: partial(lambda llm: llm, llm) for name, llm in llms.items()},
        enabled=enabled or list(llms),
        default=next(iter(llms)),
    )
    events = RecordingEvents()
    retriever = Retriever(embedder, store, top_k=2, min_score=min_score)
    return RagPipeline(retriever, registry, events), events


async def test_answer_with_citations() -> None:
    llm = FakeLLM("Backups are retained for 35 days [1].")
    pipeline, events = await make_pipeline({"fake": llm})

    result = await pipeline.answer("How long are backups retained?", conversation_id="conv-1")

    assert result.answer == "Backups are retained for 35 days [1]."
    assert not result.refused and result.refusal_reason is None
    assert [(c.number, c.doc_id, c.section) for c in result.citations] == [(1, "kb-3", "Backups")]
    assert result.conversation_id == "conv-1" and len(result.message_id) == 32
    assert (result.provider, result.model) == ("fake", "fake-1")
    assert result.usage.output_tokens == 7
    assert result.timings.time_to_first_token_ms is not None
    assert result.timings.total_ms >= result.timings.generation_ms
    assert events.results == [result]

    system, messages = llm.calls[0]
    assert "Answer only from the sources" in system
    assert "Backups are retained for 35 days." in messages[0].content
    assert messages[0].content.endswith("Question: How long are backups retained?")


async def test_low_scoring_chunks_are_not_sent_to_the_llm() -> None:
    llm = FakeLLM("Backups are retained for 35 days [1].")
    pipeline, _ = await make_pipeline({"fake": llm})
    result = await pipeline.answer("How long are backups retained?")
    assert result.sources_used == 1
    assert "HMAC" not in llm.calls[0][1][0].content


async def test_low_score_refuses_without_calling_the_llm() -> None:
    llm = FakeLLM()
    pipeline, events = await make_pipeline({"fake": llm})

    result = await pipeline.answer("zebra quantum football")

    assert result.refused and result.refusal_reason == "low_score"
    assert "Internal SME Request" in result.answer
    assert result.citations == [] and result.provider is None
    assert llm.calls == []
    assert events.results == [result]


async def test_uncited_answer_counts_as_refusal() -> None:
    pipeline, _ = await make_pipeline({"fake": FakeLLM("The knowledge base does not cover this.")})
    result = await pipeline.answer("How long are backups retained?")
    assert result.refused and result.refusal_reason == "no_citations"
    assert result.answer == "The knowledge base does not cover this."


async def test_invented_citation_numbers_are_dropped() -> None:
    pipeline, _ = await make_pipeline({"fake": FakeLLM("Retained 35 days [1]. Also [9].")})
    result = await pipeline.answer("How long are backups retained?")
    assert [c.number for c in result.citations] == [1]
    assert not result.refused


async def test_model_refusal_returns_no_answer_message() -> None:
    pipeline, _ = await make_pipeline({"fake": RefusingLLM()})
    result = await pipeline.answer("How long are backups retained?")
    assert result.refused and result.refusal_reason == "model_refusal"
    assert "Internal SME Request" in result.answer
    assert result.stop_reason == "refusal"


async def test_stream_event_order() -> None:
    pipeline, _ = await make_pipeline({"fake": FakeLLM("Kept 35 days [1].")})
    events = [e async for e in pipeline.stream("How long are backups retained?")]

    assert isinstance(events[0], SourcesEvent)
    assert [s.doc_id for s in events[0].sources] == ["kb-3"]
    deltas = [e.text for e in events if isinstance(e, AnswerDelta)]
    assert "".join(deltas) == "Kept 35 days [1]."
    assert isinstance(events[-1], Completed)
    assert events[0].message_id == events[-1].result.message_id


async def test_provider_option_selects_llm() -> None:
    default, other = FakeLLM("A [1].", name="a"), FakeLLM("B [1].", name="b")
    pipeline, _ = await make_pipeline({"a": default, "b": other})
    result = await pipeline.answer("backups retained?", options=ChatOptions(provider="b"))
    assert result.provider == "b" and other.calls and not default.calls


async def test_disabled_provider_fails_before_retrieval() -> None:
    pipeline, events = await make_pipeline({"a": FakeLLM(), "b": FakeLLM()}, enabled=["a"])
    with pytest.raises(ProviderDisabledError):
        await pipeline.answer("backups?", options=ChatOptions(provider="b"))
    assert events.results == []


async def test_log_only_event_store_logs_metrics_without_text(
    caplog: pytest.LogCaptureFixture,
) -> None:
    pipeline, _ = await make_pipeline({"fake": FakeLLM("Kept 35 days [1].")})
    result = await pipeline.answer("How long are backups retained? secret-question")
    with caplog.at_level(logging.INFO, logger="app.chat_events"):
        await LogOnlyEventStore().record(result)
    assert '"event": "chat_turn"' in caplog.text
    assert '"cited_docs": ["kb-3"]' in caplog.text
    assert "secret-question" not in caplog.text
