from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.schemas import ProviderOut, ProvidersResponse
from app.api.state import get_services
from app.api.v1.health import ollama_status
from app.providers.errors import ProviderError
from app.services import Services

router = APIRouter(tags=["providers"])


@router.get("/providers", response_model=ProvidersResponse)
async def providers(services: Annotated[Services, Depends(get_services)]) -> ProvidersResponse:
    """Enabled LLM providers and whether they can be used right now."""
    settings = services.settings
    items = []
    for name in services.llms.enabled:
        try:
            llm = services.llms.get(name)
        except ProviderError as exc:
            items.append(
                ProviderOut(name=name, model=None, default=False, available=False, detail=str(exc))
            )
            continue
        available, detail = True, None
        if name == "ollama":
            status = await ollama_status(settings)
            if not status.reachable:
                available, detail = False, "Ollama is unreachable"
            elif settings.ollama_chat_model in status.missing_models:
                available, detail = False, f"Model {settings.ollama_chat_model} is not pulled"
        items.append(
            ProviderOut(
                name=name, model=llm.model, default=False, available=available, detail=detail
            )
        )
    for item in items:
        item.default = item.name == services.llms.default
    return ProvidersResponse(default=services.llms.default, providers=items)
