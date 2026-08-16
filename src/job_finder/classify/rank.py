"""Persist final_rank for all live postings.

Pulls (posting, company) rows, passes them through `ranking.final_rank`,
and writes back the scalar. Run after Haiku triage — it depends on
fit_score/check_risk_score being populated.

Idempotent by design: re-running recomputes every row. Cheap enough at
our volumes (a few thousand live postings) that we don't bother with
incremental updates.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..db import aconn
from ..logging_config import get_logger
from ..metrics import record as record_metric
from ..ranking import RankInputs, final_rank

log = get_logger(__name__)

TARGET_PROVINCES = {"ON", "QC"}  # Toronto/Montreal; remote is handled separately


@dataclass(slots=True)
class RankReport:
    scored: int
    skipped_missing_scores: int


def _in_target(location: str | None, remote_type: str, hq_province: str | None) -> bool:
    """True if this job maps to Toronto, Montreal, or remote-Canada."""
    if remote_type == "remote":
        return True
    loc = (location or "").lower()
    if "toronto" in loc or "montreal" in loc or "montréal" in loc:
        return True
    return (hq_province or "").upper() in TARGET_PROVINCES


async def rank_all() -> RankReport:
    scored = 0
    skipped = 0
    async with aconn() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT
                    p.id,
                    p.fit_score,
                    p.check_risk_score,
                    p.first_seen,
                    p.salary_min,
                    p.salary_max,
                    p.remote_type::text AS remote_type,
                    p.location,
                    c.hq_province
                FROM postings p
                JOIN companies c ON c.id = p.company_id
                WHERE p.closed_at IS NULL
                  AND p.canonical_posting_id IS NULL
                """
            )
            rows: list[dict[str, Any]] = list(await cur.fetchall())

        for r in rows:
            if r["fit_score"] is None or r["check_risk_score"] is None:
                skipped += 1
                continue
            inp = RankInputs(
                fit_score=float(r["fit_score"]),
                check_risk_score=float(r["check_risk_score"]),
                first_seen=r["first_seen"],
                salary_min=r["salary_min"],
                salary_max=r["salary_max"],
                remote_type=r["remote_type"],
                in_target_geography=_in_target(r["location"], r["remote_type"], r["hq_province"]),
                hq_province=r["hq_province"],
            )
            score = final_rank(inp)
            async with conn.cursor() as cur:
                await cur.execute(
                    "UPDATE postings SET final_rank = %s WHERE id = %s",
                    (score, r["id"]),
                )
            scored += 1

        await conn.commit()

    log.info("rank.all.done", scored=scored, skipped=skipped)
    await record_metric("rank.all.done", scored=scored, skipped=skipped)
    return RankReport(scored=scored, skipped_missing_scores=skipped)
