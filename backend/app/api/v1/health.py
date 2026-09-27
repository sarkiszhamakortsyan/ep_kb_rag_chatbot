"""GET /health: liveness (always 200) plus readiness, meaning whether the index is loaded and
whether Ollama is reachable with the configured models pulled."""

from typing import Annotated, Literal

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel

import app
from app.api.schemas import IndexStatus
from app.api.state import AppState, get_state
from app.core.config import Settings, get_settings

router = APIRouter(tags=["health"])


class OllamaStatus(BaseModel):
    reachable: bool
    models: list[str] = []
    missing_models: list[str] = []


class HealthResponse(BaseModel):
    status: Literal["ok", "starting", "degraded"]
    ready: bool
    version: str
    llm_provider: str
    index: IndexStatus
    ollama: OllamaStatus | None = None


async def ollama_status(settings: Settings) -> OllamaStatus:
    # Only the Ollama models this configuration actually uses.
    required = set()
    if "ollama" in settings.enabled_llm_providers:
        required.add(settings.ollama_chat_model)
    if settings.embedding_provider == "ollama":
        required.add(settings.ollama_embed_model)
    try:
        async with httpx.AsyncClient(base_url=settings.ollama_base_url, timeout=3.0) as client:
            response = await client.get("/api/tags")
            response.raise_for_status()
    except httpx.HTTPError:
        return OllamaStatus(reachable=False, missing_models=sorted(required))
    models = sorted(m["name"] for m in response.json().get("models", []))
    # Ollama reports untagged models as "<name>:latest".
    available = set(models) | {m.removesuffix(":latest") for m in models}
    return OllamaStatus(reachable=True, models=models, missing_models=sorted(required - available))


@router.get("/health", response_model=HealthResponse)
async def health(
    settings: Annotated[Settings, Depends(get_settings)],
    state: Annotated[AppState, Depends(get_state)],
) -> HealthResponse:
    """Liveness (always 200) plus readiness: is the index loaded and Ollama usable?"""
    services = state.services
    if services is not None:
        index = IndexStatus(
            ready=True,
            documents=services.index.documents,
            chunks=services.index.chunks,
            embedding_model=services.index.embedding_model,
        )
    else:
        index = IndexStatus(ready=False, error=state.error)

    uses_ollama = settings.llm_provider == "ollama" or settings.embedding_provider == "ollama"
    ollama = await ollama_status(settings) if uses_ollama else None
    ollama_ok = ollama is None or (ollama.reachable and not ollama.missing_models)

    if not index.ready:
        status: Literal["ok", "starting", "degraded"] = "degraded" if state.error else "starting"
    else:
        status = "ok" if ollama_ok else "degraded"
    return HealthResponse(
        status=status,
        ready=index.ready,
        version=app.__version__,
        # The runtime default (admin Settings can change it) once the services are loaded.
        llm_provider=services.llms.default if services else settings.llm_provider,
        index=index,
        ollama=ollama,
    )
