import json
from dataclasses import asdict
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.state import get_services
from app.api.v1.admin.common import ADMIN_ERRORS, DateRange, History
from app.core.config import Settings, get_settings
from app.core.pricing import TokenCounts
from app.providers.llm.base import ChatMessage, GenerationDone, GenerationOptions, TextDelta
from app.rag.prompts import load_prompt
from app.services import Services

router = APIRouter(prefix="/costs")

ADVICE_PROVIDER = "anthropic"


class DayCostOut(BaseModel):
    day: str
    usd: float


class ModelCostOut(BaseModel):
    provider: str | None
    model: str | None
    questions: int
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    usd: float
    priced: bool


class WhatIfOut(BaseModel):
    model: str
    usd: float


class HintOut(BaseModel):
    kind: str
    title: str
    detail: str


class CostsOut(BaseModel):
    date_from: str
    date_to: str
    questions: int
    total_usd: float
    usd_per_question: float | None
    cache_savings_usd: float
    cache_share: float | None
    per_day: list[DayCostOut]
    per_model: list[ModelCostOut]
    what_if: list[WhatIfOut]
    hints: list[HintOut]


class AdviceOut(BaseModel):
    advice: str
    model: str | None
    usd: float | None  # what this advice call itself cost


@router.get("", response_model=CostsOut, responses=ADMIN_ERRORS)
async def costs(
    history: History, dates: DateRange, settings: Annotated[Settings, Depends(get_settings)]
) -> Any:
    """Estimated costs (list prices x stored token counts) with optimisation hints."""
    report = await history.costs(*dates, settings.price_table(), top_k=settings.top_k)
    return asdict(report)


@router.post("/advice", response_model=AdviceOut, responses=ADMIN_ERRORS)
async def advice(
    history: History,
    dates: DateRange,
    settings: Annotated[Settings, Depends(get_settings)],
    services: Annotated[Services, Depends(get_services)],
) -> AdviceOut:
    """Asks Claude for cost advice. Only aggregated figures are sent, never questions or
    answers. This call itself costs about $0.02 to $0.03 with Claude Opus."""
    report = await history.costs(*dates, settings.price_table(), top_k=settings.top_k)
    figures = {
        "period": [report.date_from, report.date_to],
        "questions": report.questions,
        "total_usd": round(report.total_usd, 4),
        "usd_per_question": report.usd_per_question,
        "cache_share_of_claude_input": report.cache_share,
        "cache_savings_usd": round(report.cache_savings_usd, 4),
        "per_model": [
            {k: v for k, v in asdict(m).items() if k != "priced"} for m in report.per_model
        ],
        "same_claude_turns_priced_as": {w.model: round(w.usd, 4) for w in report.what_if},
        "top_k": settings.top_k,
        "observations": [h.title for h in report.hints],
    }
    llm = services.llms.get(ADVICE_PROVIDER)
    parts: list[str] = []
    done: GenerationDone | None = None
    async for event in llm.stream(
        load_prompt("cost_advice"),
        [ChatMessage("user", json.dumps(figures, indent=2))],
        GenerationOptions(max_output_tokens=800),
    ):
        if isinstance(event, TextDelta):
            parts.append(event.text)
        else:
            done = event
    usd = None
    if done is not None:
        u = done.usage
        tokens = TokenCounts(
            u.input_tokens,
            u.output_tokens,
            u.cache_read_input_tokens,
            u.cache_creation_input_tokens,
        )
        usd = settings.price_table().cost(llm.name, done.model or llm.model, tokens, 0.0)
    return AdviceOut(
        advice="".join(parts).strip(), model=done.model if done else llm.model, usd=usd
    )
