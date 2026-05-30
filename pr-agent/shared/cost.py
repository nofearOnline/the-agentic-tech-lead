"""Token-usage accounting and cost computation, in one place so every
version reports cost identically.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Iterable

from .config import Pricing


@dataclass(frozen=True)
class Usage:
    """One Anthropic API call's token usage, broken down for cache accounting.

    Field names mirror the Anthropic SDK's `Usage` object so we can construct
    a `Usage` directly from `response.usage.__dict__` in most cases.
    """

    input_tokens: int = 0                  # uncached, billed at input price
    cache_creation_input_tokens: int = 0   # written to cache, billed at write price
    cache_read_input_tokens: int = 0       # served from cache, billed at read price
    output_tokens: int = 0

    @property
    def total_input(self) -> int:
        return (
            self.input_tokens
            + self.cache_creation_input_tokens
            + self.cache_read_input_tokens
        )

    @property
    def cache_hit_rate(self) -> float:
        if self.total_input == 0:
            return 0.0
        return self.cache_read_input_tokens / self.total_input


EMPTY_USAGE = Usage()


def add_usage(a: Usage, b: Usage) -> Usage:
    return Usage(
        input_tokens=a.input_tokens + b.input_tokens,
        cache_creation_input_tokens=(
            a.cache_creation_input_tokens + b.cache_creation_input_tokens
        ),
        cache_read_input_tokens=a.cache_read_input_tokens + b.cache_read_input_tokens,
        output_tokens=a.output_tokens + b.output_tokens,
    )


def sum_usage(items: Iterable[Usage]) -> Usage:
    out = EMPTY_USAGE
    for u in items:
        out = add_usage(out, u)
    return out


def compute_cost(usage: Usage, pricing: Pricing) -> float:
    """Return USD cost for a single call's usage at the given model's pricing."""
    return (
        usage.input_tokens * pricing.input
        + usage.cache_creation_input_tokens * pricing.input_cache_write
        + usage.cache_read_input_tokens * pricing.input_cache_read
        + usage.output_tokens * pricing.output
    ) / 1_000_000.0


def usage_from_anthropic(raw_usage) -> Usage:
    """Coerce the SDK's Usage object into our dataclass, tolerating missing fields."""
    def _get(name: str) -> int:
        value = getattr(raw_usage, name, None)
        if value is None and isinstance(raw_usage, dict):
            value = raw_usage.get(name)
        return int(value or 0)

    return Usage(
        input_tokens=_get("input_tokens"),
        cache_creation_input_tokens=_get("cache_creation_input_tokens"),
        cache_read_input_tokens=_get("cache_read_input_tokens"),
        output_tokens=_get("output_tokens"),
    )


__all__ = [
    "Usage",
    "EMPTY_USAGE",
    "add_usage",
    "sum_usage",
    "compute_cost",
    "usage_from_anthropic",
]


# Suppress unused import for `field`, `replace` — kept for downstream consumers.
_ = (field, replace)
