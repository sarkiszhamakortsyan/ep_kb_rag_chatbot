from typing import Annotated, Literal

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel

import app
from app.core.config import Settings, get_settings

router = APIRouter(tags=["health"])


class OllamaStatus(BaseModel):
    reachable: bool
    models: list[str] = []
    missing_models: list[str] = []


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    llm_provider: str
    ollama: OllamaStatus | None = None


async def _ollama_status(settings: Settings) -> OllamaStatus:
    required = {settings.ollama_chat_model, settings.ollama_embed_model}
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
async def health(settings: Annotated[Settings, Depends(get_settings)]) -> HealthResponse:
    """Liveness plus a dependency check. Always 200 so the container stays up while Ollama loads."""
    uses_ollama = settings.llm_provider == "ollama" or settings.embedding_provider == "ollama"
    ollama = await _ollama_status(settings) if uses_ollama else None
    healthy = ollama is None or (ollama.reachable and not ollama.missing_models)
    return HealthResponse(
        status="ok" if healthy else "degraded",
        version=app.__version__,
        llm_provider=settings.llm_provider,
        ollama=ollama,
    )
