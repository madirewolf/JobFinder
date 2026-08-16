"""Composite final_rank scorer.

Combines fit, check-risk, freshness, salary, remote-flex, location, and the
Quebec legal-advantage bonus into one scalar used for the UI kanban ordering
and the daily digest.

Do NOT remove the `check_risk_score` discount or the QC bonus without
re-reading SPEC §4.3 — they encode the operator's specific legal posture.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(slots=True)
class RankInputs:
    """Everything the scorer needs. Keep this flat — no DB objects."""

    fit_score: float  # 0..1
    check_risk_score: float  # 0..1
    first_seen: datetime
    salary_min: int | None = None
    salary_max: int | None = None
    remote_type: str = "unspecified"  # remote|hybrid|onsite|unspecified
    in_target_geography: bool = True  # TO/MTL/remote-Canada
    hq_province: str | None = None  # 'QC' triggers s.18.2 bonus


FRESHNESS_HALF_LIFE_HOURS = 72.0


def final_rank(i: RankInputs, now: datetime | None = None) -> float:
    now = now or datetime.now(tz=timezone.utc)
    if i.first_seen.tzinfo is None:
        first_seen = i.first_seen.replace(tzinfo=timezone.utc)
    else:
        first_seen = i.first_seen

    hours = max(0.0, (now - first_seen).total_seconds() / 3600)
    freshness = math.exp(-hours / FRESHNESS_HALF_LIFE_HOURS)

    salary_factor = _salary_factor(i.salary_min, i.salary_max)

    remote_flex = {
        "remote": 1.1,
        "hybrid": 1.05,
        "onsite": 1.0,
        "unspecified": 0.95,
    }.get(i.remote_type, 0.95)

    location_match = 1.0 if i.in_target_geography else 0.3

    qc_bonus = 1.08 if (i.hq_province or "").upper() == "QC" else 1.0

    raw = (
        i.fit_score
        * (1 - 0.6 * i.check_risk_score)
        * freshness
        * salary_factor
        * remote_flex
        * location_match
        * qc_bonus
    )
    return round(max(0.0, raw), 6)


def _salary_factor(minimum: int | None, maximum: int | None) -> float:
    """Bonus for posts that actually disclose salary, extra for the operator's
    target band ($110k-$160k CAD base, per profile/prefs.md).

    Anchored to `minimum` when present (more honest signal than `maximum`).
    Sub-floor postings get a meaningful penalty so the bot stops surfacing
    them ahead of in-band roles even when other signals look good.
    """
    if minimum is None and maximum is None:
        return 1.0  # unknown — neutral
    anchor = minimum if minimum is not None else (maximum or 0)
    if anchor >= 160_000:  # above target ceiling — bonus but capped
        return 1.30
    if anchor >= 140_000:  # upper-bullseye
        return 1.25
    if anchor >= 120_000:  # mid-bullseye
        return 1.20
    if anchor >= 110_000:  # at floor of target band
        return 1.10
    if anchor >=  90_000:  # absolute floor (per prefs.md), below target
        return 0.95
    if anchor >=  70_000:  # below floor — surface but discount
        return 0.75
    return 0.5  # well below floor — strong discount
