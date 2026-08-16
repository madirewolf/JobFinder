"""Ingestion orchestrator.

Dispatches the configured ATS clients against the seeded `companies` rows,
normalizes output, upserts, and records metrics. Designed to be called from:
  - `jfb ingest run --source greenhouse --company cohere`
  - `jfb ingest all`
  - a systemd timer per-source
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from ..ats import REGISTRY
from ..db import aconn
from ..logging_config import get_logger
from .repository import record_metric, resolve_company_id, upsert_posting

log = get_logger(__name__)


@dataclass(slots=True)
class IngestResult:
    source: str
    token: str
    fetched: int = 0
    inserted: int = 0
    updated: int = 0
    dup_skipped: int = 0
    errors: int = 0

    def add(self, action: str) -> None:
        if action == "inserted":
            self.inserted += 1
        elif action == "updated":
            self.updated += 1
        elif action == "dup_skipped":
            self.dup_skipped += 1


async def run_one(source: str, token: str) -> IngestResult:
    """Run a single (source, token) pair end-to-end."""
    fetcher = REGISTRY.get(source)
    if fetcher is None:
        raise ValueError(f"unknown source {source!r}; known: {sorted(REGISTRY)}")

    result = IngestResult(source=source, token=token)

    try:
        postings = await fetcher(token)
    except Exception as e:  # noqa: BLE001
        log.error("ingest.fetch.fail", source=source, token=token, err=str(e))
        result.errors += 1
        return result

    result.fetched = len(postings)

    async with aconn() as conn:
        company_id = await resolve_company_id(conn, token, source)
        if company_id is None:
            log.warning("ingest.company.not_seeded", source=source, token=token)
            await record_metric(conn, "ingest.skip.unseeded", source=source, token=token)
            return result

        for p in postings:
            try:
                _, action = await upsert_posting(conn, company_id, p)
                result.add(action)
            except Exception as e:  # noqa: BLE001
                log.warning(
                    "ingest.upsert.fail",
                    source=source,
                    token=token,
                    url=p.url_canonical,
                    err=str(e),
                )
                result.errors += 1

        await record_metric(
            conn,
            "ingest.done",
            source=source,
            token=token,
            fetched=result.fetched,
            inserted=result.inserted,
            updated=result.updated,
            dup_skipped=result.dup_skipped,
            errors=result.errors,
        )
        await conn.commit()

    log.info(
        "ingest.done",
        source=source,
        token=token,
        fetched=result.fetched,
        inserted=result.inserted,
        updated=result.updated,
        dup_skipped=result.dup_skipped,
        errors=result.errors,
    )
    return result


async def run_source(source: str, concurrency: int = 3) -> list[IngestResult]:
    """Run a source against every seeded company configured for it."""
    async with aconn() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT ats_token FROM companies
                WHERE active = TRUE
                  AND ats_platform = %s::ats_platform_enum
                  AND ats_token IS NOT NULL
                ORDER BY tier, name
                """,
                (source,),
            )
            tokens = [r["ats_token"] for r in await cur.fetchall()]

    log.info("ingest.source.start", source=source, companies=len(tokens))
    sem = asyncio.Semaphore(concurrency)

    async def _guarded(tok: str) -> IngestResult:
        async with sem:
            return await run_one(source, tok)

    return await asyncio.gather(*(_guarded(t) for t in tokens))


async def run_all(concurrency: int = 3) -> dict[str, list[IngestResult]]:
    """Run every known source, each with internal bounded concurrency."""
    out: dict[str, list[IngestResult]] = {}
    for source in sorted(REGISTRY):
        out[source] = await run_source(source, concurrency=concurrency)
    return out
