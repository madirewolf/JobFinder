"""Retrieve portfolio chunks for drafting.

Two retrieval flavors:
  - `top_for_system()` — top-K chunks against the aggregate `profile_vectors.primary`,
    used to build the cached system prefix (stable across all drafts)
  - `top_for_posting()` — top-K chunks against a specific posting's embedding,
    used in the per-application user message for RAG grounding

Stable ordering by posting id ensures the cached prefix text is byte-identical
call-to-call; a different order changes the prompt and busts the cache.
"""

from __future__ import annotations

from typing import Any

from ..db import aconn
from ..logging_config import get_logger
from .types import PortfolioChunk

__all__ = ["PortfolioChunk", "top_for_system", "top_for_posting", "fetch_posting",
           "SYSTEM_CHUNKS_DEFAULT", "POSTING_CHUNKS_DEFAULT"]

log = get_logger(__name__)

SYSTEM_CHUNKS_DEFAULT = 40
POSTING_CHUNKS_DEFAULT = 8


async def top_for_system(k: int = SYSTEM_CHUNKS_DEFAULT) -> list[PortfolioChunk]:
    """Top-K portfolio chunks by cosine to the aggregate profile vector.

    Re-orders the retrieved set by `id` before returning, so the concatenated
    text is byte-stable across calls (cache-friendly).
    """
    async with aconn() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                WITH pv AS (
                    SELECT embedding FROM profile_vectors WHERE label = 'primary' LIMIT 1
                )
                SELECT pc.id, pc.source, pc.project, pc.content,
                       (pc.embedding <=> (SELECT embedding FROM pv)) AS cos_dist
                FROM portfolio_chunks pc
                WHERE EXISTS (SELECT 1 FROM pv)
                ORDER BY pc.embedding <=> (SELECT embedding FROM pv) ASC
                LIMIT %s
                """,
                (k,),
            )
            rows = list(await cur.fetchall())
    # Re-sort by id for cache stability
    rows.sort(key=lambda r: r["id"])
    return [
        PortfolioChunk(
            id=r["id"],
            source=r["source"],
            project=r["project"],
            content=r["content"],
            cos_dist=float(r["cos_dist"]),
        )
        for r in rows
    ]


async def top_for_posting(posting_id: int, k: int = POSTING_CHUNKS_DEFAULT) -> list[PortfolioChunk]:
    """Top-K portfolio chunks by cosine to this posting's embedding.

    Returned in retrieval (cosine-ascending) order so the most relevant
    chunk comes first in the user message.
    """
    async with aconn() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                WITH pe AS (
                    SELECT embedding FROM posting_embeddings WHERE posting_id = %s
                )
                SELECT pc.id, pc.source, pc.project, pc.content,
                       (pc.embedding <=> (SELECT embedding FROM pe)) AS cos_dist
                FROM portfolio_chunks pc
                WHERE EXISTS (SELECT 1 FROM pe)
                ORDER BY pc.embedding <=> (SELECT embedding FROM pe) ASC
                LIMIT %s
                """,
                (posting_id, k),
            )
            rows = list(await cur.fetchall())
    return [
        PortfolioChunk(
            id=r["id"],
            source=r["source"],
            project=r["project"],
            content=r["content"],
            cos_dist=float(r["cos_dist"]),
        )
        for r in rows
    ]


async def fetch_posting(posting_id: int) -> dict[str, Any] | None:
    """Pull everything the drafter needs about one posting."""
    async with aconn() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT p.id, p.title, p.description_text, p.url_canonical,
                       p.location, p.remote_type::text AS remote_type,
                       p.salary_min, p.salary_max, p.salary_currency,
                       p.tech_stack, p.role_category, p.fit_score, p.final_rank,
                       c.name AS company_name, c.hq_city, c.hq_province,
                       c.bg_check_stringency::text AS bg_check_stringency
                FROM postings p
                JOIN companies c ON c.id = p.company_id
                WHERE p.id = %s
                """,
                (posting_id,),
            )
            return await cur.fetchone()
