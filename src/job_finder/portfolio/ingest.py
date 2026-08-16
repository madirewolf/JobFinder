"""Portfolio-site ingest: crawl → chunk → embed → insert.

Run once per site, monthly. Each site owns a `source_key` (e.g. 'limiliminal')
and ingest replaces only rows with that key so runs stay isolated — you can
re-crawl vimy without nuking 5gcx.

The aggregate profile vector is NOT recomputed here; `jfb profile ingest`
still owns that. Run it after all portfolio sites have been crawled.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..classify.chunking import chunk_text
from ..classify.embeddings import embed_batch, format_for_pgvector
from ..db import aconn
from ..logging_config import get_logger
from ..metrics import record as record_metric
from .crawler import CrawlReport, crawl_site
from .extract import ExtractedPage

log = get_logger(__name__)

# Well-known portfolio sites per spec §5.1. Users override via CLI if needed.
DEFAULT_SITES: dict[str, str] = {
    "limiliminal": "https://limiliminal.com",
    "5gcx": "https://5gcx.ai",
    "vimy": "https://vimy.ai",
}


@dataclass(slots=True)
class SiteIngestReport:
    source_key: str
    pages_crawled: int
    chunks_inserted: int
    errors: int


async def ingest_site(
    source_key: str,
    start_url: str,
    *,
    max_pages: int = 30,
    delay: float = 0.5,
) -> SiteIngestReport:
    """Crawl and store chunks for one portfolio site."""
    report = await crawl_site(start_url, max_pages=max_pages, delay=delay)

    if not report.pages:
        log.warning("portfolio.ingest.no_pages", site=source_key, start=start_url)
        return SiteIngestReport(
            source_key=source_key,
            pages_crawled=0,
            chunks_inserted=0,
            errors=report.errors,
        )

    # Chunk every page's extracted text. Stash per-chunk metadata so later
    # retrieval can surface source URLs in the drafter's system block.
    plans: list[tuple[ExtractedPage, str, dict[str, Any]]] = []
    for page in report.pages:
        for c in chunk_text(page.text):
            meta = {
                "url": page.url,
                "title": page.title,
                "char_len": len(c.text),
            }
            plans.append((page, c.text, meta))

    if not plans:
        log.warning("portfolio.ingest.empty_chunks", site=source_key, pages=len(report.pages))
        return SiteIngestReport(
            source_key=source_key,
            pages_crawled=len(report.pages),
            chunks_inserted=0,
            errors=report.errors,
        )

    texts = [t for (_, t, _) in plans]
    log.info(
        "portfolio.ingest.embedding",
        site=source_key,
        pages=len(report.pages),
        chunks=len(texts),
    )
    vectors = await embed_batch(texts, concurrency=4)

    async with aconn() as conn:
        # Idempotent per source: wipe old chunks for this key, then reinsert.
        async with conn.cursor() as cur:
            await cur.execute(
                "DELETE FROM portfolio_chunks WHERE source = %s",
                (source_key,),
            )

        for (_page, text, meta), vec in zip(plans, vectors, strict=True):
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    INSERT INTO portfolio_chunks (source, project, content, embedding, metadata)
                    VALUES (%s, NULL, %s, %s::vector, %s::jsonb)
                    """,
                    (
                        source_key,
                        text,
                        format_for_pgvector(vec),
                        _json_dumps(meta),
                    ),
                )

        await conn.commit()

    await record_metric(
        "portfolio.ingest.done",
        site=source_key,
        pages=len(report.pages),
        chunks=len(vectors),
        errors=report.errors,
    )
    return SiteIngestReport(
        source_key=source_key,
        pages_crawled=len(report.pages),
        chunks_inserted=len(vectors),
        errors=report.errors,
    )


async def ingest_all(
    *,
    sites: dict[str, str] | None = None,
    max_pages: int = 30,
    delay: float = 0.5,
) -> list[SiteIngestReport]:
    """Run every site in `sites` (defaults to DEFAULT_SITES)."""
    sites = sites or DEFAULT_SITES
    out: list[SiteIngestReport] = []
    for key, url in sites.items():
        r = await ingest_site(key, url, max_pages=max_pages, delay=delay)
        out.append(r)
    return out


async def ingest_github_readme(
    owner_repo: str,
    *,
    ref: str = "HEAD",
) -> SiteIngestReport:
    """Fetch a GitHub repo's README.md via the raw content endpoint, chunk,
    embed, and store under source key 'github:<owner>/<repo>'.

    Kept minimal on purpose — GitHub public READMEs don't need auth and the
    raw endpoint redirects to a stable edge URL.
    """
    import httpx

    source_key = f"github:{owner_repo}"
    url = f"https://raw.githubusercontent.com/{owner_repo}/{ref}/README.md"

    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        resp = await client.get(url)
    if resp.status_code != 200 or not resp.text.strip():
        log.warning("portfolio.github.miss", repo=owner_repo, status=resp.status_code)
        return SiteIngestReport(
            source_key=source_key, pages_crawled=0, chunks_inserted=0, errors=1
        )

    chunks = chunk_text(resp.text)
    texts = [c.text for c in chunks]
    if not texts:
        return SiteIngestReport(
            source_key=source_key, pages_crawled=1, chunks_inserted=0, errors=0
        )
    vectors = await embed_batch(texts, concurrency=4)

    async with aconn() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "DELETE FROM portfolio_chunks WHERE source = %s",
                (source_key,),
            )
        for c, vec in zip(chunks, vectors, strict=True):
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    INSERT INTO portfolio_chunks (source, project, content, embedding, metadata)
                    VALUES (%s, %s, %s, %s::vector, %s::jsonb)
                    """,
                    (
                        source_key,
                        owner_repo.split("/", 1)[-1],
                        c.text,
                        format_for_pgvector(vec),
                        _json_dumps({"url": url, "repo": owner_repo}),
                    ),
                )
        await conn.commit()

    await record_metric(
        "portfolio.github.done",
        repo=owner_repo,
        chunks=len(vectors),
    )
    return SiteIngestReport(
        source_key=source_key,
        pages_crawled=1,
        chunks_inserted=len(vectors),
        errors=0,
    )


def _json_dumps(obj: Any) -> str:
    import json

    return json.dumps(obj, default=str)


# Re-export so callers can construct reports in tests/fixtures
__all__ = [
    "DEFAULT_SITES",
    "SiteIngestReport",
    "CrawlReport",
    "ingest_site",
    "ingest_all",
    "ingest_github_readme",
]
