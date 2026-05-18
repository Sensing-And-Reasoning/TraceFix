"""LLM API cost estimation for runtime experiments.

Prices are in USD per 1,000,000 tokens (input, output).
All figures are estimates — verify against your provider's current pricing.
"""
from __future__ import annotations

# (input_price_per_1M, output_price_per_1M) in USD
# For reasoning models, reasoning tokens are already included in output tokens.
_PRICES: dict[str, tuple[float, float]] = {
    # OpenAI GPT-5 family (estimates — update when official prices published)
    "gpt-5":        (2.50, 10.00),
    "gpt-5-mini":   (0.40,  1.60),
    "gpt-5-nano":   (0.10,  0.40),
    # OpenAI GPT-4o family
    "gpt-4o":       (2.50, 10.00),
    "gpt-4o-mini":  (0.15,  0.60),
    # OpenAI o-series
    "o3":           (10.00, 40.00),
    "o4-mini":      ( 1.10,  4.40),
    # Anthropic Claude 4 family
    "claude-opus-4":    (15.00, 75.00),
    "claude-sonnet-4":  ( 3.00, 15.00),
    "claude-haiku-4":   ( 0.80,  4.00),
}


def get_prices(model: str) -> tuple[float, float] | None:
    """Return (input_price, output_price) per 1M tokens, or None if unknown."""
    if model in _PRICES:
        return _PRICES[model]
    # Prefix match: "gpt-5-mini-2026-01-01" → "gpt-5-mini"
    for prefix, prices in _PRICES.items():
        if model.startswith(prefix):
            return prices
    return None


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float | None:
    """Return estimated USD cost, or None if model pricing is unknown."""
    prices = get_prices(model)
    if prices is None:
        return None
    in_p, out_p = prices
    return (input_tokens * in_p + output_tokens * out_p) / 1_000_000


def format_cost(model: str, input_tokens: int, output_tokens: int) -> str:
    """Return a human-readable cost string, e.g. '~$0.0042' or 'N/A'."""
    cost = estimate_cost(model, input_tokens, output_tokens)
    return f"~${cost:.4f}" if cost is not None else "N/A"
