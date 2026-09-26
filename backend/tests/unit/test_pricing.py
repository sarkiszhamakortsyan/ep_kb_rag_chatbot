import pytest

from app.core.pricing import ModelPrice, PriceTable, TokenCounts

TOKENS = TokenCounts(input=1_000_000, output=100_000, cache_read=2_000_000, cache_write=0)


def test_claude_cost_uses_every_token_type() -> None:
    table = PriceTable()
    # 1M x $5 + 0.1M x $25 + 2M x $0.50
    assert table.cost("anthropic", "claude-opus-5", TOKENS, 0) == pytest.approx(8.5)


def test_longest_prefix_and_overrides() -> None:
    table = PriceTable(
        {"claude-opus-5-special": ModelPrice(input=1, output=1, cache_read=0, cache_write=0)}
    )
    assert table.price_for("claude-opus-5-20260101") == PriceTable().price_for("claude-opus-5")
    assert table.price_for("claude-opus-5-special-x").input == 1  # type: ignore[union-attr]
    assert table.price_for("gpt-9") is None and table.price_for(None) is None


def test_local_early_refusal_and_unknown_models() -> None:
    assert PriceTable().cost("ollama", "ministral-3:3b", TOKENS, 60_000) == 0.0
    assert PriceTable(local_cost_per_hour=3.6).cost("ollama", "x", TOKENS, 60_000) == pytest.approx(
        0.06
    )
    assert PriceTable().cost(None, None, TOKENS, 0) == 0.0
    assert PriceTable().cost("anthropic", "unknown-model", TOKENS, 0) is None
