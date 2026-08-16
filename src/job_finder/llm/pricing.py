"""Anthropic list pricing as of April 2026.

USD per 1M tokens. Cache write is 1.25× input; cache read is 0.10× input.
Update here when list price changes, not inline at call sites.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ModelPrice:
    input_per_mtok: float
    output_per_mtok: float

    @property
    def cache_write_per_mtok(self) -> float:
        return self.input_per_mtok * 1.25

    @property
    def cache_read_per_mtok(self) -> float:
        return self.input_per_mtok * 0.10


PRICING: dict[str, ModelPrice] = {
    # Aliases for the latest snapshot of each tier — keep both so callers
    # can use the short name without dating themselves.
    "claude-haiku-4-5": ModelPrice(1.0, 5.0),
    "claude-haiku-4-5-20251001": ModelPrice(1.0, 5.0),
    "claude-sonnet-4-6": ModelPrice(3.0, 15.0),
    "claude-opus-4-7": ModelPrice(5.0, 25.0),
}


def usd_cost(
    model: str,
    *,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
) -> float:
    """Compute billed USD for one Messages API call.

    `input_tokens` here is the non-cached portion; cache_read + cache_write are
    the separate portions reported by the API in `usage.cache_*_input_tokens`.
    """
    price = PRICING.get(model)
    if price is None:
        return 0.0  # unknown model — don't silently miscount
    return (
        input_tokens / 1_000_000 * price.input_per_mtok
        + output_tokens / 1_000_000 * price.output_per_mtok
        + cache_read_tokens / 1_000_000 * price.cache_read_per_mtok
        + cache_write_tokens / 1_000_000 * price.cache_write_per_mtok
    )
