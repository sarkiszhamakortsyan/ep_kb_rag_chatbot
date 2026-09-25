import json
import logging
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.api.errors import error_payload
from app.api.schemas import ChatRequest, ChatResponse, CitationOut, ErrorResponse
from app.api.state import get_services
from app.rag.pipeline import AnswerDelta, ChatOptions, Completed, SourcesEvent
from app.services import Services

router = APIRouter(tags=["chat"])
logger = logging.getLogger(__name__)

ERRORS: dict[int | str, dict[str, object]] = {
    400: {"model": ErrorResponse, "description": "Unknown or disabled provider"},
    422: {"model": ErrorResponse, "description": "Invalid request"},
    502: {"model": ErrorResponse, "description": "The LLM provider returned an error"},
    503: {"model": ErrorResponse, "description": "Index loading, or provider unavailable"},
}


@router.post("/chat", response_model=ChatResponse, responses=ERRORS)
async def chat(
    request: ChatRequest, services: Annotated[Services, Depends(get_services)]
) -> ChatResponse:
    """Answer a question from the knowledge base, with citations."""
    result = await services.pipeline.answer(
        request.message,
        conversation_id=request.conversation_id,
        options=ChatOptions(provider=request.options.provider),
    )
    return ChatResponse.from_result(result)


@router.post(
    "/chat/stream",
    responses={
        **ERRORS,
        200: {
            "content": {"text/event-stream": {}},
            "description": (
                "Server-Sent Events: `meta` (ids + candidate sources), `token` ({text}), "
                "`done` (the full ChatResponse), or `error` ({code, message})."
            ),
        },
    },
)
async def chat_stream(
    request: ChatRequest, services: Annotated[Services, Depends(get_services)]
) -> StreamingResponse:
    """Same as /chat, but streams the answer token by token."""
    # Resolve the provider before the stream starts, so config errors are plain HTTP errors.
    services.llms.get(request.options.provider)
    return StreamingResponse(
        _events(request, services),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _events(request: ChatRequest, services: Services) -> AsyncIterator[str]:
    try:
        async for event in services.pipeline.stream(
            request.message,
            conversation_id=request.conversation_id,
            options=ChatOptions(provider=request.options.provider),
        ):
            if isinstance(event, SourcesEvent):
                yield _sse(
                    "meta",
                    {
                        "conversation_id": event.conversation_id,
                        "message_id": event.message_id,
                        "sources": [
                            CitationOut.from_citation(s).model_dump() for s in event.sources
                        ],
                    },
                )
            elif isinstance(event, AnswerDelta):
                yield _sse("token", {"text": event.text})
            elif isinstance(event, Completed):
                yield _sse("done", ChatResponse.from_result(event.result).model_dump())
    except Exception as exc:
        # Headers are already sent, so errors travel as an SSE event.
        _, code, message = error_payload(exc)
        if code == "internal_error":
            logger.exception("Streaming chat failed")
        else:
            logger.warning("Streaming chat failed: %s", exc)
        yield _sse("error", {"code": code, "message": message})


def _sse(event: str, data: object) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
