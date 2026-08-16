"""DB access for ingestion. Keeps SQL in one place."""

from __future__ import annotations

import json
from typing import Any

from ..logging_config import get_logger
from ..models import RawPosting
from ..utils.hashing import normalize_title, title_company_hash

log = get_logger(__name__)


async def resolve_company_id(conn, company_token: str, ats_platform: str) -> int | None:
    """Look up a seeded company by ats_platform + ats_token.

    Returns None if not seeded. The orchestrator decides whether to insert a
    discovered company or skip it.
    """
    async with conn.cursor() as cur:
        await cur.execute(
            """
            SELECT id FROM companies
            WHERE ats_platform = %s::ats_platform_enum
              AND ats_token = %s
              AND active = TRUE
            LIMIT 1
            """,
            (ats_platform, company_token),
        )
        row = await cur.fetchone()
        return row["id"] if row else None


async def insert_discovered_company(
    conn,
    *,
    name: str,
    ats_platform: str,
    ats_token: str,
) -> int:
    """Insert a company not in the seed list, flagged for human review."""
    async with conn.cursor() as cur:
        await cur.execute(
            """
            INSERT INTO companies
                (name, ats_platform, ats_token, bg_check_stringency, tier, notes, active)
            VALUES
                (%s, %s::ats_platform_enum, %s, 'unknown', 99, 'auto-discovered', TRUE)
            ON CONFLICT (name, domain) DO UPDATE SET updated_at = now()
            RETURNING id
            """,
            (name, ats_platform, ats_token),
        )
        row = await cur.fetchone()
        return row["id"]


async def upsert_posting(conn, company_id: int, p: RawPosting) -> tuple[int, str]:
    """Insert-or-update a posting. Returns (posting_id, action).

    action ∈ {"inserted", "updated", "reposted", "dup_skipped"}.

    Behaviour:
      - First collision on url_canonical → bump last_seen, reposted_count += 1 → "updated".
      - Different url_canonical but same title_company_hash for a live posting →
        insert as a new row with canonical_posting_id set → "dup_skipped".
      - Fresh row → "inserted".
    """
    t_norm = normalize_title(p.title)
    tch = title_company_hash(p.title, p.company_name)
    raw_json = json.dumps(p.raw_json)

    async with conn.cursor() as cur:
        # 1. Try to update existing row by canonical URL.
        await cur.execute(
            """
            UPDATE postings
            SET last_seen = now(),
                reposted_count = reposted_count + 1,
                description_text = %s,
                raw_json = %s::jsonb
            WHERE url_canonical = %s
            RETURNING id
            """,
            (p.description_text, raw_json, p.url_canonical),
        )
        row = await cur.fetchone()
        if row:
            return row["id"], "updated"

        # 2. Check if an existing live posting has the same title_company_hash.
        await cur.execute(
            """
            SELECT id FROM postings
            WHERE title_company_hash = %s
              AND canonical_posting_id IS NULL
              AND closed_at IS NULL
            LIMIT 1
            """,
            (tch,),
        )
        dup = await cur.fetchone()
        canonical_posting_id = dup["id"] if dup else None

        # 3. Insert new row.
        await cur.execute(
            """
            INSERT INTO postings (
                company_id, title, title_normalized, url_canonical,
                source, source_rank, raw_json, description_text,
                location, remote_type, title_company_hash, canonical_posting_id
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s::remote_type_enum, %s, %s)
            RETURNING id
            """,
            (
                company_id,
                p.title,
                t_norm,
                p.url_canonical,
                p.source,
                p.source_rank,
                raw_json,
                p.description_text,
                p.location_raw,
                _remote_enum(p.remote_raw),
                tch,
                canonical_posting_id,
            ),
        )
        row = await cur.fetchone()
        posting_id: int = row["id"]
        return posting_id, ("dup_skipped" if canonical_posting_id else "inserted")


def _remote_enum(raw: str | None) -> str:
    if not raw:
        return "unspecified"
    r = raw.strip().lower().replace("_", "-")
    if "remote" in r or "work from home" in r or "wfh" in r:
        return "remote"
    if "hybrid" in r:
        return "hybrid"
    if "on-site" in r or "onsite" in r or "in-office" in r:
        return "onsite"
    return "unspecified"


async def record_metric(conn, metric: str, value: float = 1, **tags: Any) -> None:
    async with conn.cursor() as cur:
        await cur.execute(
            "INSERT INTO metric_events (metric, value, tags) VALUES (%s, %s, %s::jsonb)",
            (metric, value, json.dumps(tags)),
        )
