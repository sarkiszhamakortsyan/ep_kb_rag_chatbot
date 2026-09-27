"""An EventStore that keeps the last turns of each conversation in memory, so follow-up questions
work even when the SQLite history is switched off."""

from collections import OrderedDict, deque
from typing import TYPE_CHECKING

from app.stores.events.base import EventStore, Turns

if TYPE_CHECKING:
    from app.rag.pipeline import ChatResult


class InMemoryConversations(EventStore):
    """Recent turns per conversation, kept in memory (bounded). Used for follow-up questions
    when the SQLite history is switched off; lost on restart."""

    def __init__(self, max_conversations: int = 1000, turns_per_conversation: int = 5) -> None:
        self._max = max_conversations
        self._per = turns_per_conversation
        self._turns: OrderedDict[str, deque[tuple[str, str]]] = OrderedDict()

    async def record(self, result: "ChatResult") -> None:
        turns = self._turns.pop(result.conversation_id, None) or deque(maxlen=self._per)
        turns.append((result.question, result.answer))
        self._turns[result.conversation_id] = turns  # most recently used last
        while len(self._turns) > self._max:
            self._turns.popitem(last=False)

    async def recent_turns(self, conversation_id: str, limit: int) -> Turns:
        return list(self._turns.get(conversation_id, ()))[-limit:]
