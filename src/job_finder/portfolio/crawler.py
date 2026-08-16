"""Breadth-first same-origin crawler for personal-portfolio sites.

Small and deliberately boring. We're fetching our own sites (limiliminal,
5gcx, vimy) so there's no politeness-policy drama — a 0.5s delay and a
sane page cap are plenty.

Public surface:
    async def crawl_site(start_url, *, max_pages=30, delay=0.5) -> list[ExtractedPage]

Dependencies imported lazily so `tests/test_portfolio_extract.py` can import
the package without httpx on PATH.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from ..logging_config import get_logger
from .extract import ExtractedPage, extract_page, same_origin

log = get_logger(__name__)

DEFAULT_MAX_PAGES = 30
DEFAULT_DELAY_S = 0.5
DEFAULT_TIMEOUT_S = 10.0
DEFAULT_UA = "JobFinderBot/0.1 (personal portfolio crawler; +contact=self)"


@dataclass(slots=True)
class CrawlReport:
    start_url: str
    pages: list[ExtractedPage]
    skipped: int
    errors: int


async def crawl_site(
    start_url: str,
    *,
    max_pages: int = DEFAULT_MAX_PAGES,
    delay: float = DEFAULT_DELAY_S,
    timeout: float = DEFAULT_TIMEOUT_S,
    user_agent: str = DEFAULT_UA,
) -> CrawlReport:
    """BFS crawl of `start_url`'s same-origin pages. Returns extracted text."""
    import httpx  # lazy

    visited: set[str] = set()
    queue: list[str] = [start_url]
    results: list[ExtractedPage] = []
    errors = 0

    async with httpx.AsyncClient(
        timeout=timeout,
        headers={"User-Agent": user_agent, "Accept-Language": "en-CA,en;q=0.9"},
        follow_redirects=True,
        http2=True,
    ) as client:
        while queue and len(results) < max_pages:
            url = queue.pop(0)
            if url in visited:
                continue
            visited.add(url)

            try:
                resp = await client.get(url)
            except Exception as e:  # noqa: BLE001
                errors += 1
                log.warning("portfolio.fetch.fail", url=url, err=str(e))
                continue

            ctype = resp.headers.get("content-type", "")
            if resp.status_code != 200 or "html" not in ctype.lower():
                log.debug(
                    "portfolio.fetch.skip",
                    url=url,
                    status=resp.status_code,
                    ctype=ctype,
                )
                continue

            page = extract_page(resp.text, url)
            if page.text:
                results.append(page)
            else:
                log.debug("portfolio.fetch.empty", url=url)

            # Enqueue same-origin links we haven't visited
            for href in page.links:
                if href in visited:
                    continue
                if not same_origin(href, start_url):
                    continue
                queue.append(href)

            await asyncio.sleep(delay)

    skipped = len(visited) - len(results) - errors
    log.info(
        "portfolio.crawl.done",
        start_url=start_url,
        pages=len(results),
        visited=len(visited),
        errors=errors,
    )
    return CrawlReport(start_url=start_url, pages=results, skipped=skipped, errors=errors)
