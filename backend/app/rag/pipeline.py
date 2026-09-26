"""The RAG pipeline: (rewrite a follow-up) -> retrieve -> (refuse early) -> prompt -> generate
-> cite.

Every turn ends in a `ChatResult` holding the answer plus everything the future admin
features need (usage, timings, scores, refusal reason): ideas.md "Future-readiness design".
"""

import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Literal

from app.providers.llm.base import (
    ChatMessage,
    GenerationDone,
    GenerationOptions,
    LLMProvider,
    TextDelta,
    Usage,
)
from app.providers.llm.registry import LLMRegistry
from app.rag.citations import Citation, build_citations, strip_markers, to_citation
from app.rag.prompts import build_user_message, load_prompt, system_prompt
from app.rag.retrieval import Retriever
from app.stores.events.base import EventStore, Turns

RefusalReason = Literal["low_score", "no_citations", "model_refusal"]

# Follow-up questions: how many earlier turns are shown to the rewrite step, and how much of
# each earlier answer (the question and the start of the answer carry the topic).
CONTEXT_TURNS = 3
CONTEXT_ANSWER_CHARS = 500


@dataclass(frozen=True)
class ChatOptions:
    # LLM provider for this turn; None = the configured default (ideas.md #7).
    provider: str | None = None
    # "detailed" asks for a complete explanation instead of a concise answer (ideas.md #3).
    detail: Literal["concise", "detailed"] = "concise"
    # ISO code from prompts.LANGUAGES; None = answer in the question's language (ideas.md #4).
    language: str | None = None


@dataclass(frozen=True)
class Timings:
    embed_ms: float = 0.0
    search_ms: float = 0.0
    time_to_first_token_ms: float | None = None  # from the start of the turn
    generation_ms: float = 0.0
    total_ms: float = 0.0
    rewrite_ms: float = 0.0  # follow-up rewriting (0 for a first question)


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
    language: str | None = None  # requested answer language (ideas.md #4)
    # A follow-up rewritten as a self-contained question, when it differs from `question`.
    standalone_question: str | None = None


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
        # Resolve the provider first so a disabled/unknown provider fails before any work.
        llm = self._llms.get(options.provider)

        # A follow-up ("and on Enterprise?") is rewritten into a self-contained question first,
        # so retrieval and the answer know the topic. First questions skip this LLM call.
        standalone: str | None = None
        rewrite = GenerationDone(usage=Usage())
        rewrite_ms = 0.0
        turns = (
            await self._events.recent_turns(conversation_id, CONTEXT_TURNS)
            if conversation_id
            else []
        )
        if turns:
            rewrite_started = time.perf_counter()
            standalone, rewrite = await self._rewrite(llm, question, turns)
            rewrite_ms = _ms(rewrite_started)
        asked = standalone or question

        conversation_id = conversation_id or uuid.uuid4().hex
        message_id = uuid.uuid4().hex
        retrieval = await self._retriever.retrieve(asked)
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
                usage=rewrite.usage,
                timings=Timings(
                    embed_ms=retrieval.embed_ms,
                    search_ms=retrieval.search_ms,
                    total_ms=_ms(started),
                    rewrite_ms=rewrite_ms,
                ),
                top_score=retrieval.top_score,
                sources_used=len(sources),
                language=options.language,
                standalone_question=standalone,
            )
            await self._events.record(result)
            yield Completed(result)
            return

        generation_started = time.perf_counter()
        first_token: float | None = None
        parts: list[str] = []
        done = GenerationDone(usage=Usage())
        async for event in llm.stream(
            system_prompt(options.detail, options.language),
            [ChatMessage("user", build_user_message(asked, sources))],
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
            usage=_add(done.usage, rewrite.usage),
            stop_reason=done.stop_reason,
            timings=Timings(
                embed_ms=retrieval.embed_ms,
                search_ms=retrieval.search_ms,
                time_to_first_token_ms=first_token,
                generation_ms=_ms(generation_started),
                total_ms=_ms(started),
                rewrite_ms=rewrite_ms,
            ),
            top_score=retrieval.top_score,
            sources_used=len(sources),
            language=options.language,
            standalone_question=standalone,
        )
        await self._events.record(result)
        yield Completed(result)

    async def _rewrite(
        self, llm: LLMProvider, question: str, turns: Turns
    ) -> tuple[str | None, GenerationDone]:
        """The follow-up as a self-contained question; None when the model keeps it as is."""
        context = "\n\n".join(
            f"User: {q}\nAssistant: {strip_markers(a)[:CONTEXT_ANSWER_CHARS]}" for q, a in turns
        )
        parts: list[str] = []
        done = GenerationDone(usage=Usage())
        async for event in llm.stream(
            load_prompt("rewrite_question"),
            [ChatMessage("user", f"Conversation:\n{context}\n\nNew question: {question}")],
            GenerationOptions(temperature=0.0, max_output_tokens=150),
        ):
            if isinstance(event, TextDelta):
                parts.append(event.text)
            else:
                done = event
        lines = "".join(parts).strip().splitlines()
        # Small models sometimes wrap the line in quotes or Markdown bold: drop those.
        rewritten = lines[0].strip().strip("\"'*`").strip() if lines else ""
        # Keep the original on an empty, runaway or unchanged result.
        if not rewritten or len(rewritten) > 4 * len(question) + 200:
            return None, done
        if rewritten.casefold() == question.strip().casefold():
            return None, done
        return rewritten, done

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


def _add(a: Usage, b: Usage) -> Usage:
    return Usage(
        input_tokens=a.input_tokens + b.input_tokens,
        output_tokens=a.output_tokens + b.output_tokens,
        cache_read_input_tokens=a.cache_read_input_tokens + b.cache_read_input_tokens,
        cache_creation_input_tokens=a.cache_creation_input_tokens + b.cache_creation_input_tokens,
    )


def _ms(since: float) -> float:
    return round((time.perf_counter() - since) * 1000, 1)
