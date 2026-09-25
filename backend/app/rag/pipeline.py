"""The RAG pipeline: retrieve -> (refuse early) -> prompt -> generate -> cite.

Every turn ends in a `ChatResult` holding the answer plus everything the future admin
features need (usage, timings, scores, refusal reason): ideas.md "Future-readiness design".
"""

import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Literal

from app.providers.llm.base import ChatMessage, GenerationDone, GenerationOptions, TextDelta, Usage
from app.providers.llm.registry import LLMRegistry
from app.rag.citations import Citation, build_citations, to_citation
from app.rag.prompts import build_user_message, load_prompt
from app.rag.retrieval import Retriever
from app.stores.events.base import EventStore

RefusalReason = Literal["low_score", "no_citations", "model_refusal"]


@dataclass(frozen=True)
class ChatOptions:
    # LLM provider for this turn; None = the configured default (ideas.md #7).
    provider: str | None = None


@dataclass(frozen=True)
class Timings:
    embed_ms: float = 0.0
    search_ms: float = 0.0
    time_to_first_token_ms: float | None = None  # from the start of the turn
    generation_ms: float = 0.0
    total_ms: float = 0.0


@dataclass(frozen=True)
class ChatResult:
    conversation_id: str
    message_id: str
    question: str
    answer: str
    citations: list[Citation]
    refused: bool
    refusal_reason: RefusalReason | None
    provider: str | None  # None when no LLM was called (low-score refusal)
    model: str | None
    usage: Usage
    timings: Timings
    top_score: float
    sources_used: int  # chunks passed to the LLM
    stop_reason: str | None = None
    language: str | None = None  # reserved for multi-language support (ideas.md #4)


@dataclass(frozen=True)
class SourcesEvent:
    """Emitted before generation: candidate sources (citations are resolved at the end)."""

    conversation_id: str
    message_id: str
    sources: list[Citation] = field(default_factory=list)


@dataclass(frozen=True)
class AnswerDelta:
    text: str


@dataclass(frozen=True)
class Completed:
    result: ChatResult


PipelineEvent = SourcesEvent | AnswerDelta | Completed


class RagPipeline:
    def __init__(
        self,
        retriever: Retriever,
        llms: LLMRegistry,
        events: EventStore,
        *,
        generation: GenerationOptions | None = None,
    ) -> None:
        self._retriever = retriever
        self._llms = llms
        self._events = events
        self._generation = generation or GenerationOptions()

    async def stream(
        self,
        question: str,
        *,
        conversation_id: str | None = None,
        options: ChatOptions | None = None,
    ) -> AsyncIterator[PipelineEvent]:
        options = options or ChatOptions()
        started = time.perf_counter()
        conversation_id = conversation_id or uuid.uuid4().hex
        message_id = uuid.uuid4().hex
        # Resolve the provider first so a disabled/unknown provider fails before any work.
        llm = self._llms.get(options.provider)

        retrieval = await self._retriever.retrieve(question)
        # Low-scoring chunks are noise: leave them out of the prompt (fewer tokens, less confusion).
        sources = [r for r in retrieval.results if r.score >= self._retriever.min_score]
        yield SourcesEvent(
            conversation_id,
            message_id,
            [to_citation(n, r) for n, r in enumerate(sources, start=1)],
        )

        if not retrieval.covered:
            # Nothing relevant in the KB: refuse without spending an LLM call.
            answer = load_prompt("no_answer")
            yield AnswerDelta(answer)
            result = ChatResult(
                conversation_id=conversation_id,
                message_id=message_id,
                question=question,
                answer=answer,
                citations=[],
                refused=True,
                refusal_reason="low_score",
                provider=None,
                model=None,
                usage=Usage(),
                timings=Timings(
                    embed_ms=retrieval.embed_ms,
                    search_ms=retrieval.search_ms,
                    total_ms=_ms(started),
                ),
                top_score=retrieval.top_score,
                sources_used=len(sources),
            )
            await self._events.record(result)
            yield Completed(result)
            return

        generation_started = time.perf_counter()
        first_token: float | None = None
        parts: list[str] = []
        done = GenerationDone(usage=Usage())
        async for event in llm.stream(
            load_prompt("system"),
            [ChatMessage("user", build_user_message(question, sources))],
            self._generation,
        ):
            if isinstance(event, TextDelta):
                if first_token is None:
                    first_token = _ms(started)
                parts.append(event.text)
                yield AnswerDelta(event.text)
            else:
                done = event

        answer = "".join(parts).strip()
        citations = build_citations(answer, sources)
        refusal_reason: RefusalReason | None = None
        if done.stop_reason == "refusal":
            refusal_reason = "model_refusal"
        elif not citations:
            # The prompt forbids citations in "not covered" answers, so an uncited answer is
            # treated as a refusal (this works in any reply language).
            refusal_reason = "no_citations"
        if refusal_reason == "model_refusal" and not answer:
            answer = load_prompt("no_answer")
            yield AnswerDelta(answer)

        result = ChatResult(
            conversation_id=conversation_id,
            message_id=message_id,
            question=question,
            answer=answer,
            citations=citations,
            refused=refusal_reason is not None,
            refusal_reason=refusal_reason,
            provider=llm.name,
            model=done.model or llm.model,
            usage=done.usage,
            stop_reason=done.stop_reason,
            timings=Timings(
                embed_ms=retrieval.embed_ms,
                search_ms=retrieval.search_ms,
                time_to_first_token_ms=first_token,
                generation_ms=_ms(generation_started),
                total_ms=_ms(started),
            ),
            top_score=retrieval.top_score,
            sources_used=len(sources),
        )
        await self._events.record(result)
        yield Completed(result)

    async def answer(
        self,
        question: str,
        *,
        conversation_id: str | None = None,
        options: ChatOptions | None = None,
    ) -> ChatResult:
        """Non-streaming convenience wrapper."""
        async for event in self.stream(question, conversation_id=conversation_id, options=options):
            if isinstance(event, Completed):
                return event.result
        raise RuntimeError("Pipeline finished without a result")


def _ms(since: float) -> float:
    return round((time.perf_counter() - since) * 1000, 1)
