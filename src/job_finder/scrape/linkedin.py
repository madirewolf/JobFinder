"""LinkedIn public-jobs scraper (no login).

Spec TKT-061. Search by `(keyword, location)` tuples from a small keyword
list × {Toronto, Montreal, Remote Canada}. 24h cadence.

**This is a skeleton** — the DOM selectors for LinkedIn's public search
page drift frequently and pinning them in code without manual verification
would give false confidence. The scrape harness (`.harness.managed_context`)
provides the browser; the search URL builder and result DTO are pinned here
so the call sites are stable.

Fill in `_parse_results_page()` when you're ready to run a production scrape;
the rest of the pipeline (dedup, classify, rank, draft) doesn't change.
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

PUBLIC_SEARCH_BASE = "https://www.linkedin.com/jobs/search"

# Locations we feed the search. Keep it small — each tuple is one browser nav.
DEFAULT_LOCATIONS: tuple[str, ...] = (
    "Toronto, Ontario, Canada",
    "Montreal, Quebec, Canada",
    "Canada",  # used together with "remote" filter
)

# Conservative default list; override per-run.
DEFAULT_KEYWORDS: tuple[str, ...] = (
    "graphics programmer",
    "machine learning engineer",
    "systems software engineer",
)


@dataclass(slots=True)
class SearchSpec:
    keyword: str
    location: str
    remote_only: bool = False


def build_search_url(spec: SearchSpec) -> str:
    """Construct a public LinkedIn jobs search URL.

    Params documented on LinkedIn's own "copy link" UX:
      f_WT=2 → remote only (work type = 2)
      f_TPR=r86400 → posted within 24 hours
    """
    qs: dict[str, str] = {
        "keywords": spec.keyword,
        "location": spec.location,
        "f_TPR": "r86400",
        "geoId": "",  # leave LinkedIn to infer from `location`
    }
    if spec.remote_only:
        qs["f_WT"] = "2"
    return f"{PUBLIC_SEARCH_BASE}?{urlencode(qs)}"


async def search_public(
    specs: list[SearchSpec] | None = None,
    *,
    max_per_spec: int = 25,
    cfg: HarnessConfig | None = None,
) -> list[RawPosting]:
    """Run every (keyword, location) pair, return `RawPosting` rows.

    On CAPTCHA, that spec's results are skipped and a metric is logged —
    we do not attempt to solve (burn-risk vs. value isn't worth it for a
    personal bot).
    """
    specs = specs or [
        SearchSpec(keyword=k, location=loc, remote_only=("Remote" in loc))
        for k in DEFAULT_KEYWORDS
        for loc in DEFAULT_LOCATIONS
    ]

    out: list[RawPosting] = []
    async with managed_context(cfg) as ctx:
        page = await ctx.new_page()
        for spec in specs:
            url = build_search_url(spec)
            log.info("scrape.linkedin.nav", keyword=spec.keyword, loc=spec.location)
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=20_000)
            except Exception as e:  # noqa: BLE001
                log.warning("scrape.linkedin.nav.fail", err=str(e), url=url)
                continue

            if await degrade_on_captcha(page):
                continue

            await human_pause(1.2, 0.5)

            postings = await _parse_results_page(page, spec=spec, cap=max_per_spec)
            log.info(
                "scrape.linkedin.result",
                keyword=spec.keyword,
                loc=spec.location,
                n=len(postings),
            )
            out.extend(postings)

            await human_pause(2.0, 0.8)

    return out


async def _parse_results_page(
    page: Page,  # type: ignore[name-defined]
    *,
    spec: SearchSpec,
    cap: int,
) -> list[RawPosting]:
    """Extract postings from the current LinkedIn results DOM.

    **SKELETON:** DOM selectors drift — pin them here only after a manual
    verification pass. Returning `[]` keeps the pipeline safe when they break.

    Suggested approach:
      1. Wait for `ul.jobs-search__results-list` (or the current equivalent).
      2. Iterate `li` cards; pull the `a[href]` for each job URL.
      3. For each, click (or navigate in a new tab) and parse the detail
         view; convert to `RawPosting` with `source="linkedin"`.

    For now the skeleton returns nothing rather than feeding garbage into
    Postgres. The call wiring above IS tested — see `tests/test_scrape_harness.py`.
    """
    log.debug("scrape.linkedin.parse.skeleton", spec=spec.__dict__, cap=cap)
    return []
