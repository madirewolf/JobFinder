"""Pure data types for the drafter (no DB imports — safe for test isolation)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class PortfolioChunk:
    id: int
    source: str
    project: str | None
    content: str
    cos_dist: float
