"""Runtime settings (ideas.md #7): switch model providers on/off and pick the default without a
restart. The configuration (.env) is the upper limit: only providers in ENABLED_LLM_PROVIDERS can
be enabled here. Changes are stored in SQLite and applied again at the next startup."""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from app.api.state import get_services
from app.api.v1.admin.common import ADMIN_ERRORS, History
from app.providers.errors import ProviderDisabledError
from app.services import Services
from app.stores.history.sqlite import SqliteHistory

router = APIRouter(prefix="/settings")
logger = logging.getLogger(__name__)

MODEL_POLICY_KEY = "llm_providers"


class ProviderSetting(BaseModel):
    name: str
    model: str | None
    enabled: bool
    default: bool


class SettingsOut(BaseModel):
    providers: list[ProviderSetting]
    embedding_provider: str
    embedding_model: str


class SettingsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled_providers: list[str] = Field(min_length=1)
    default_provider: str


def apply_stored_policy(services: Services, history: SqliteHistory | None) -> None:
    """Re-applies the admin's last choice; ignored (with a warning) if .env no longer allows it."""
    stored = history.get_setting(MODEL_POLICY_KEY) if history else None
    if not stored:
        return
    try:
        services.llms.configure(stored["enabled"], stored["default"])
    except (ProviderDisabledError, KeyError, TypeError) as exc:
        logger.warning("Ignoring the stored model settings (%s); using .env instead", exc)


def _settings_out(services: Services) -> SettingsOut:
    models = {
        "ollama": services.settings.ollama_chat_model,
        "anthropic": services.settings.anthropic_model,
    }
    items = [
        ProviderSetting(
            name=name,
            model=models.get(name),
            enabled=name in services.llms.enabled,
            default=name == services.llms.default,
        )
        for name in services.llms.allowed
    ]
    embedder = services.embeddings.get()
    return SettingsOut(
        providers=items, embedding_provider=embedder.name, embedding_model=embedder.model
    )


@router.get("", response_model=SettingsOut, responses=ADMIN_ERRORS)
async def read_settings(services: Annotated[Services, Depends(get_services)]) -> Any:
    """The providers the configuration allows, which are enabled, and the default."""
    return _settings_out(services)


@router.put("", response_model=SettingsOut, responses=ADMIN_ERRORS)
async def update_settings(
    body: SettingsIn,
    history: History,
    services: Annotated[Services, Depends(get_services)],
) -> Any:
    """Enables/disables providers and sets the default, immediately and for future restarts."""
    services.llms.configure(body.enabled_providers, body.default_provider)
    await history.set_setting(
        MODEL_POLICY_KEY, {"enabled": services.llms.enabled, "default": services.llms.default}
    )
    return _settings_out(services)
