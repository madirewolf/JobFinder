"""Indeed Canada scraper (spec TKT-062).

Cloudflare is the main antagonist. Defense posture:
  - Canadian UA + en-CA locale via the harness
  - Randomized human pauses (no tight polling loops)
  - Residential proxy via env (PROXY_SERVER etc.) when configured
  - Detect interstitials via `degrade_on_captcha()` and abandon the run

Skeleton mirror of `linkedin.py` — URL builder is pinned here so callers
have a stable API; `_parse_results_page()` returns `[]` until DOM selectors
are verified by hand.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING
from urllib.parse import urlencode

from .harness import HarnessConfig, degrade_on_captcha, human_pause, managed_context

if TYPE_CHECKING:  # pragma: no cover
    from playwright.async_api import Page

    from ..models import RawPosting

log = logging.getLogger(__name__)

SEARCH_BASE = "https://ca.indeed.com/jobs"

DEFAULT_LOCATIONS: tuple[str, ...] = (
    "Toronto, ON",
    "Montreal, QC",
    "Remote",
)

DEFAULT_KEYWORDS: tuple[str, ...] = (
    "graphics engineer",
    "ml engineer",
    "backend engineer",
)


@dataclass(slots=True)
class SearchSpec:
    keyword: str
    location: str
    posted_within_days: int = 1


def build_search_url(spec: SearchSpec) -> str:
    """Indeed public search URL.

    `fromage=<N>` is "posted within N days". `sort=date` to match the
    "newest first" heuristic other pipelines rely on.
    """
    qs: dict[str, str] = {
        "q": spec.keyword,
        "l": spec.location,
        "fromage": str(max(1, spec.posted_within_days)),
        "sort": "date",
    }
    return f"{SEARCH_BASE}?{urlencode(qs)}"


async def search_canada(
    specs: list[SearchSpec] | None = None,
    *,
    max_per_spec: int = 25,
    cfg: HarnessConfig | None = None,
) -> list[RawPosting]:
    """Run every spec; return normalized postings."""
    specs = specs or [
        SearchSpec(keyword=k, location=loc)
        for k in DEFAULT_KEYWORDS
        for loc in DEFAULT_LOCATIONS
    ]

    out: list[RawPosting] = []
    async with managed_context(cfg) as ctx:
        page = await ctx.new_page()
        for spec in specs:
            url = build_search_url(spec)
            log.info("scrape.indeed.nav", keyword=spec.keyword, loc=spec.location)
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=25_000)
            except Exception as e:  # noqa: BLE001
                log.warning("scrape.indeed.nav.fail", err=str(e), url=url)
                continue

            if await degrade_on_captcha(page):
                continue

            # Indeed loves an initial slow reveal — give the list a beat.
            await human_pause(1.8, 0.6)

            postings = await _parse_results_page(page, spec=spec, cap=max_per_spec)
            log.info(
                "scrape.indeed.result",
                keyword=spec.keyword,
                loc=spec.location,
                n=len(postings),
            )
            out.extend(postings)

            await human_pause(2.5, 1.0)

    return out


async def _parse_results_page(
    page: Page,  # type: ignore[name-defined]
    *,
    spec: SearchSpec,
    cap: int,
) -> list[RawPosting]:
    """Extract postings from Indeed's DOM.

    **SKELETON** — see `linkedin._parse_results_page()` for the pattern.
    When wiring for real, prefer JSON-LD `<script type="application/ld+json">`
    blocks over CSS selectors; Indeed emits structured JobPosting metadata
    on many cards and it drifts less than the rendered DOM.
    """
    log.debug("scrape.indeed.parse.skeleton", spec=spec.__dict__, cap=cap)
    return []
