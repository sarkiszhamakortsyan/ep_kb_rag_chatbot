"""Token prices for the costs tab (ideas.md #2).

Costs are estimates computed from the stored token counts and the prices below, so a price
change applies to past turns too. Defaults are Anthropic list prices in USD per million tokens
(cache writes = 1.25 x input for the 5-minute cache, cache reads = 0.1 x input); override them with
MODEL_PRICES (JSON) when prices change or for other models. Local models have no API price: their
optional cost is LOCAL_COST_PER_HOUR (e.g. a GPU server's hourly price) x generation time.
"""

from dataclasses import dataclass

from pydantic import BaseModel, Field


class ModelPrice(BaseModel):
    """USD per million tokens."""

    input: float = Field(ge=0)
    output: float = Field(ge=0)
    cache_read: float = Field(ge=0)
    cache_write: float = Field(ge=0)


DEFAULT_PRICES: dict[str, ModelPrice] = {
    "claude-opus-5": ModelPrice(input=5.0, output=25.0, cache_read=0.5, cache_write=6.25),
    "claude-sonnet-5": ModelPrice(input=3.0, output=15.0, cache_read=0.3, cache_write=3.75),
    "claude-haiku-4-5": ModelPrice(input=1.0, output=5.0, cache_read=0.1, cache_write=1.25),
}


@dataclass(frozen=True)
class TokenCounts:
    input: int  # not served from the cache
    output: int
    cache_read: int
    cache_write: int


class PriceTable:
    def __init__(
        self, overrides: dict[str, ModelPrice] | None = None, local_cost_per_hour: float = 0.0
    ) -> None:
        self.prices = {**DEFAULT_PRICES, **(overrides or {})}
        self.local_cost_per_hour = local_cost_per_hour

    def price_for(self, model: str | None) -> ModelPrice | None:
        """Longest matching prefix, so "claude-opus-5-20260101" uses the "claude-opus-5" price."""
        if not model:
            return None
        matches = [key for key in self.prices if model.startswith(key)]
        return self.prices[max(matches, key=len)] if matches else None

    def cost(
        self, provider: str | None, model: str | None, tokens: TokenCounts, generation_ms: float
    ) -> float | None:
        """USD for one turn; 0 when no model ran; None for a cloud model without a price."""
        if provider is None:
            return 0.0  # refused before any LLM call
        if provider == "ollama":
            return self.local_cost_per_hour * generation_ms / 3_600_000
        price = self.price_for(model)
        if price is None:
            return None
        return token_cost(price, tokens)


def token_cost(price: ModelPrice, tokens: TokenCounts) -> float:
    return (
        tokens.input * price.input
        + tokens.output * price.output
        + tokens.cache_read * price.cache_read
        + tokens.cache_write * price.cache_write
    ) / 1_000_000
