"""Embed postings that don't yet have a row in `posting_embeddings`.

Runs as a worker-style loop: grab a batch of un-embedded postings with
`FOR UPDATE SKIP LOCKED` so multiple instances don't step on each other,
embed each, and upsert the vector. Intentionally small per-batch so long
backlogs don't hold one transaction open for minutes.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..db import aconn
from ..logging_config import get_logger
from .embeddings import embed_batch, format_for_pgvector

log = get_logger(__name__)

DEFAULT_BATCH = 32
DESCRIPTION_PREFIX_CHARS = 1500  # per spec §5 — cheap embedding input budget


@dataclass(slots=True)
class EmbedReport:
    embedded: int
    remaining: int


def _embed_text(title: str, description: str) -> str:
    """What we actually feed the embedder — title gets weight by being up front."""
    return f"{title.strip()}\n\n{(description or '').strip()[:DESCRIPTION_PREFIX_CHARS]}"


async def _count_pending(conn) -> int:
    async with conn.cursor() as cur:
        await cur.execute(
            """
            SELECT COUNT(*) AS n
            FROM postings p
            LEFT JOIN posting_embeddings e ON e.posting_id = p.id
            WHERE e.posting_id IS NULL
              AND p.closed_at IS NULL
              AND p.canonical_posting_id IS NULL
            """
        )
        row = await cur.fetchone()
        return int(row["n"] or 0)


async def embed_pending(batch_size: int = DEFAULT_BATCH, max_batches: int = 20) -> EmbedReport:
    """Embed pending postings in bounded batches.

    Stops after `max_batches * batch_size` rows or when no more are pending,
    whichever comes first. The outer caller (a CLI or a cron worker) should
    re-invoke us to drain larger backlogs.
    """
    total_embedded = 0

    for _ in range(max_batches):
        async with aconn() as conn:
            # SKIP LOCKED on the parent row means concurrent workers don't
            # fight over the same posting.
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT p.id, p.title, p.description_text
                    FROM postings p
                    LEFT JOIN posting_embeddings e ON e.posting_id = p.id
                    WHERE e.posting_id IS NULL
                      AND p.closed_at IS NULL
                      AND p.canonical_posting_id IS NULL
                    ORDER BY p.first_seen DESC
                    LIMIT %s
                    FOR UPDATE OF p SKIP LOCKED
                    """,
                    (batch_size,),
                )
                rows = await cur.fetchall()

            if not rows:
                await conn.commit()
                break

            texts = [_embed_text(r["title"], r["description_text"]) for r in rows]
            vectors = await embed_batch(texts, concurrency=4)

            async with conn.cursor() as cur:
                for row, vec in zip(rows, vectors, strict=True):
                    await cur.execute(
                        """
                        INSERT INTO posting_embeddings (posting_id, embedding)
                        VALUES (%s, %s::vector)
                        ON CONFLICT (posting_id) DO UPDATE
                            SET embedding = EXCLUDED.embedding,
                                created_at = now()
                        """,
                        (row["id"], format_for_pgvector(vec)),
                    )
            await conn.commit()
            total_embedded += len(rows)
            log.info("embed.batch.ok", n=len(rows), total=total_embedded)

    async with aconn() as conn:
        remaining = await _count_pending(conn)

    log.info("embed.done", embedded=total_embedded, remaining=remaining)
    return EmbedReport(embedded=total_embedded, remaining=remaining)
