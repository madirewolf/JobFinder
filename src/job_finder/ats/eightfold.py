"""Eightfold AI careers API (used by Ericsson, some Fortune 500).

Pattern (confirmed working for Ericsson):
    POST https://{company}.eightfold.ai/api/apply/v2/jobs
    Query: ?domain={company}.com&start=0&num=50&location=Canada
    Body:  empty JSON object {}

Response: {"positions": [...], "count": N}. Each position has:
    name, job_id, locations[], business_unit, department,
    display_job_description (HTML), canonicalPositionUrl

Implement when Ericsson hiring heats up; Ericsson Canada hiring is steady
but this bot's ATS coverage already finds most Canadian tech without it.
"""

from __future__ import annotations

from ..logging_config import get_logger
from ..models import RawPosting

log = get_logger(__name__)


async def fetch(token: str) -> list[RawPosting]:
    log.warning(
        "eightfold.fetch.not_implemented",
        token=token,
        hint="See module docstring. Ericsson token = 'ericsson'.",
    )
    return []
