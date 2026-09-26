from collections.abc import AsyncIterator, Sequence
from pathlib import Path

import pytest

from app.providers.llm.base import (
    ChatMessage,
    GenerationDone,
    GenerationOptions,
    StreamEvent,
    TextDelta,
    Usage,
)
from app.rag.pipeline import ChatOptions
from app.stores.events.fanout import FanOutEventStore
from app.stores.events.memory import InMemoryConversations
from app.stores.history.sqlite import SqliteHistory
from tests.fakes import FakeLLM
from tests.unit.test_pipeline import RecordingEvents, make_pipeline

pytestmark = pytest.mark.anyio


class ScriptedLLM(FakeLLM):
    """Answers normally, but returns `rewritten` when asked to rewrite a follow-up."""

    def __init__(self, rewritten: str) -> None:
        super().__init__("Backups are retained for 35 days [1].")
        self.rewritten = rewritten

    async def stream(
        self,
        system: str,
        messages: Sequence[ChatMessage],
        options: GenerationOptions | None = None,
    ) -> AsyncIterator[StreamEvent]:
        if "rewrite follow-up questions" in system:
            self.calls.append((system, list(messages)))
            yield TextDelta(self.rewritten)
            yield GenerationDone(usage=Usage(input_tokens=100, output_tokens=10))
            return
        async for event in super().stream(system, messages, options):
            yield event


async def pipeline_with_memory(llm: FakeLLM):  # type: ignore[no-untyped-def]
    pipeline, recorder = await make_pipeline({"fake": llm})
    pipeline._events = FanOutEventStore([recorder, InMemoryConversations()])
    return pipeline


async def test_a_follow_up_is_rewritten_before_retrieval() -> None:
    llm = ScriptedLLM("How long are backups retained on the Enterprise plan?")
    pipeline = await pipeline_with_memory(llm)

    first = await pipeline.answer("How long are backups retained?")
    assert (
        first.standalone_question is None and len(llm.calls) == 1
    )  # no rewrite for a first question

    follow_up = await pipeline.answer("And on Enterprise?", conversation_id=first.conversation_id)

    assert follow_up.question == "And on Enterprise?"
    assert follow_up.standalone_question == "How long are backups retained on the Enterprise plan?"
    _, rewrite_messages = llm.calls[1]
    assert "User: How long are backups retained?" in rewrite_messages[0].content
    assert "[1]" not in rewrite_messages[0].content  # citation markers removed from context
    answer_messages = llm.calls[2][1]
    assert answer_messages[0].content.endswith(
        "Question: How long are backups retained on the Enterprise plan?"
    )
    assert follow_up.usage.input_tokens > 100  # rewrite + answer
    assert len(llm.calls) == 3  # answer, rewrite, answer (rewrite_ms is timed; too fast to assert)


async def test_an_unchanged_or_empty_rewrite_keeps_the_question() -> None:
    follow_up = "And backups retained on Enterprise?"
    for rewritten in (follow_up, ""):
        llm = ScriptedLLM(rewritten)
        pipeline = await pipeline_with_memory(llm)
        first = await pipeline.answer("How long are backups retained?")
        result = await pipeline.answer(follow_up, conversation_id=first.conversation_id)
        assert result.standalone_question is None
        assert llm.calls[-1][1][0].content.endswith(f"Question: {follow_up}")


async def test_formatting_around_the_rewrite_is_removed() -> None:
    llm = ScriptedLLM('**"How long are backups retained on Enterprise?"**')
    pipeline = await pipeline_with_memory(llm)
    first = await pipeline.answer("How long are backups retained?")
    result = await pipeline.answer("And on Enterprise?", conversation_id=first.conversation_id)
    assert result.standalone_question == "How long are backups retained on Enterprise?"


async def test_no_memory_means_no_rewrite() -> None:
    llm = ScriptedLLM("unused")
    pipeline, _ = await make_pipeline({"fake": llm})  # recording events only: no remembered turns
    first = await pipeline.answer("backups retained?")
    await pipeline.answer("backups retained there?", conversation_id=first.conversation_id)
    assert len(llm.calls) == 2  # two answers, no rewrite call


async def test_in_memory_conversations_are_bounded() -> None:
    memory = InMemoryConversations(max_conversations=2, turns_per_conversation=2)
    pipeline, _ = await make_pipeline({"fake": FakeLLM("A [1].")})
    pipeline._events = memory
    ids = []
    for _ in range(3):
        result = await pipeline.answer("backups retained?")
        ids.append(result.conversation_id)
    for question in ("q1 backups?", "q2 backups?", "q3 backups?"):
        await pipeline.answer(question, options=ChatOptions(), conversation_id=ids[2])
    assert await memory.recent_turns(ids[0], 5) == []  # evicted (oldest conversation)
    turns = await memory.recent_turns(ids[2], 5)
    assert [q for q, _ in turns] == ["q2 backups?", "q3 backups?"]  # last two only


async def test_sqlite_history_returns_recent_turns_oldest_first(tmp_path: Path) -> None:
    history = SqliteHistory(tmp_path / "h.sqlite", retention_days=30)
    history.open()
    pipeline, _ = await make_pipeline({"fake": FakeLLM("A [1].")})
    pipeline._events = FanOutEventStore([RecordingEvents(), history])
    first = await pipeline.answer("backups retained?")
    for question in ("second backups?", "third backups?", "fourth backups?"):
        await pipeline.answer(question, conversation_id=first.conversation_id)
    turns = await history.recent_turns(first.conversation_id, 3)
    assert [q for q, _ in turns] == ["second backups?", "third backups?", "fourth backups?"]
    history.close()
