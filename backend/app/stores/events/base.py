"""Per-turn event hook. The MVP only logs; the stats/costs/history features (ideas.md #1, #2, #5)
will add a SQLite implementation of this interface without touching the pipeline."""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.rag.pipeline import ChatResult


class EventStore(ABC):
    @abstractmethod
    async def record(self, result: "ChatResult") -> None:
        """Called exactly once per chat turn, after the answer is complete."""
