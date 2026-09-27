"""An EventStore that passes every chat turn to several stores, for example the log and the
SQLite history."""

from collections.abc import Sequence
from typing import TYPE_CHECKING

from app.stores.events.base import EventStore, Turns

if TYPE_CHECKING:
    from app.rag.pipeline import ChatResult


class FanOutEventStore(EventStore):
    """Passes every turn to several stores (e.g. the structured log and the history)."""

    def __init__(self, stores: Sequence[EventStore]) -> None:
        self._stores = list(stores)

    async def record(self, result: "ChatResult") -> None:
        for store in self._stores:
            await store.record(result)

    async def recent_turns(self, conversation_id: str, limit: int) -> Turns:
        for store in self._stores:
            turns = await store.recent_turns(conversation_id, limit)
            if turns:
                return turns
        return []
