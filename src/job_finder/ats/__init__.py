"""ATS client registry.

Every client is a plain async function with signature:
    async def fetch(company_token: str) -> list[RawPosting]

Register here so the orchestrator can dispatch by name.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from ..models import RawPosting
from . import ashby, greenhouse, lever, smartrecruiters, workable, workday

Fetcher = Callable[[str], Awaitable[list[RawPosting]]]

REGISTRY: dict[str, Fetcher] = {
    "greenhouse": greenhouse.fetch,
    "lever": lever.fetch,
    "ashby": ashby.fetch,
    "smartrecruiters": smartrecruiters.fetch,
    "workable": workable.fetch,
    "workday": workday.fetch,
    # TODO(Sprint 1): "eightfold", "recruitee"
}


def available_sources() -> list[str]:
    return sorted(REGISTRY.keys())
