import json
import logging
from typing import TYPE_CHECKING

from app.stores.events.base import EventStore

if TYPE_CHECKING:
    from app.rag.pipeline import ChatResult

logger = logging.getLogger("app.chat_events")


class LogOnlyEventStore(EventStore):
    """Writes one structured log line per turn: metrics only, no question or answer text."""

    async def record(self, result: "ChatResult") -> None:
        logger.info(
            json.dumps(
                {
                    "event": "chat_turn",
                    "conversation_id": result.conversation_id,
                    "message_id": result.message_id,
                    "provider": result.provider,
                    "model": result.model,
                    "refused": result.refused,
                    "refusal_reason": result.refusal_reason,
                    "top_score": round(result.top_score, 4),
                    "sources_used": result.sources_used,
                    "cited_docs": sorted({c.doc_id for c in result.citations}),
                    "input_tokens": result.usage.input_tokens,
                    "output_tokens": result.usage.output_tokens,
                    "cache_read_input_tokens": result.usage.cache_read_input_tokens,
                    "ttft_ms": result.timings.time_to_first_token_ms,
                    "total_ms": result.timings.total_ms,
                }
            )
        )
