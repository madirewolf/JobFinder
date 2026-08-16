"""Idempotent seed loader. Safe to run repeatedly.

Inserts new companies and updates mutable fields (ats_token, stringency, tier,
notes) on the rest. Does NOT overwrite `active`, `bg_check_reasoning`, or
`headcount_est` once set — those are human-curated.
"""

from __future__ import annotations

from ..db import conn
from ..logging_config import get_logger
from .companies import SEED_COMPANIES

log = get_logger(__name__)


def load() -> tuple[int, int]:
    """Insert or update all seeded companies. Returns (inserted, updated)."""
    inserted = 0
    updated = 0

    with conn() as c:
        with c.cursor() as cur:
            for row in SEED_COMPANIES:
                (
                    name,
                    domain,
                    ats_platform,
                    ats_token,
                    stringency,
                    tier,
                    hq_city,
                    hq_province,
                    notes,
                ) = row

                cur.execute(
                    """
                    INSERT INTO companies
                        (name, domain, ats_platform, ats_token,
                         bg_check_stringency, tier, hq_city, hq_province, notes)
                    VALUES
                        (%s, %s, %s::ats_platform_enum, %s,
                         %s::bg_stringency_enum, %s, %s, %s, %s)
                    ON CONFLICT (name, domain) DO UPDATE SET
                        ats_platform = EXCLUDED.ats_platform,
                        ats_token = EXCLUDED.ats_token,
                        bg_check_stringency = EXCLUDED.bg_check_stringency,
                        tier = EXCLUDED.tier,
                        hq_city = EXCLUDED.hq_city,
                        hq_province = EXCLUDED.hq_province,
                        notes = EXCLUDED.notes,
                        updated_at = now()
                    RETURNING (xmax = 0) AS inserted
                    """,
                    (name, domain, ats_platform, ats_token, stringency, tier, hq_city, hq_province, notes),
                )
                result = cur.fetchone()
                if result and result["inserted"]:
                    inserted += 1
                else:
                    updated += 1
        c.commit()

    log.info("seeds.load.ok", inserted=inserted, updated=updated, total=len(SEED_COMPANIES))
    return inserted, updated
