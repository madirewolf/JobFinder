"""Shared Playwright harness with en-CA locale, America/Toronto timezone.

Goals (per spec TKT-060):
  - Real-enough browser fingerprint: en-CA, America/Toronto, Canadian UA
  - Randomized human-ish delays between actions
  - Residential-proxy support via env vars (PROXY_SERVER / PROXY_USER / PROXY_PASS)
  - CAPTCHA-aware: detect and back off rather than crash the pipeline

The helpers here are tiny and synchronous-friendly; scrapers drive the
actual page flow.
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - type-only imports
    from playwright.async_api import Browser, BrowserContext, Page

# stdlib logger keeps the module importable in bare test envs (no structlog).
log = logging.getLogger(__name__)


class MissingBrowserDep(RuntimeError):
    """Raised when playwright isn't installed.

    Install with: `uv pip install -e '.[browser]' && playwright install chromium`
    """


DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15"
)
DEFAULT_VIEWPORT = {"width": 1440, "height": 900}
DEFAULT_LOCALE = "en-CA"
DEFAULT_TZ = "America/Toronto"


@dataclass(slots=True)
class HarnessConfig:
    headless: bool = True
    slow_mo_ms: int = 0
    user_agent: str = DEFAULT_UA
    locale: str = DEFAULT_LOCALE
    timezone_id: str = DEFAULT_TZ
    proxy_server: str | None = None
    proxy_username: str | None = None
    proxy_password: str | None = None

    @classmethod
    def from_env(cls) -> HarnessConfig:
        """Pull proxy creds / headless flag from env. Safe no-ops when unset."""
        return cls(
            headless=os.getenv("SCRAPE_HEADLESS", "1") != "0",
            slow_mo_ms=int(os.getenv("SCRAPE_SLOWMO_MS", "0") or 0),
            user_agent=os.getenv("SCRAPE_UA", DEFAULT_UA),
            locale=os.getenv("SCRAPE_LOCALE", DEFAULT_LOCALE),
            timezone_id=os.getenv("SCRAPE_TZ", DEFAULT_TZ),
            proxy_server=os.getenv("PROXY_SERVER") or None,
            proxy_username=os.getenv("PROXY_USER") or None,
            proxy_password=os.getenv("PROXY_PASS") or None,
        )


def _ensure_playwright() -> Any:
    """Import playwright or raise a friendly MissingBrowserDep."""
    try:
        from playwright.async_api import async_playwright
    except ImportError as e:
        raise MissingBrowserDep(
            "playwright is not installed. Run:\n"
            "  uv pip install -e '.[browser]'\n"
            "  playwright install chromium"
        ) from e
    return async_playwright


@asynccontextmanager
async def managed_context(cfg: HarnessConfig | None = None):
    """Yield a ready-to-use Playwright `BrowserContext` with our defaults.

    Usage:
        async with managed_context() as ctx:
            page = await ctx.new_page()
            await page.goto(url)
    """
    cfg = cfg or HarnessConfig.from_env()
    async_playwright = _ensure_playwright()

    proxy = None
    if cfg.proxy_server:
        proxy = {"server": cfg.proxy_server}
        if cfg.proxy_username:
            proxy["username"] = cfg.proxy_username
        if cfg.proxy_password:
            proxy["password"] = cfg.proxy_password

    async with async_playwright() as p:
        browser: Browser = await p.chromium.launch(
            headless=cfg.headless,
            slow_mo=cfg.slow_mo_ms,
            proxy=proxy,
        )
        try:
            context: BrowserContext = await browser.new_context(
                user_agent=cfg.user_agent,
                viewport=DEFAULT_VIEWPORT,
                locale=cfg.locale,
                timezone_id=cfg.timezone_id,
                extra_http_headers={"Accept-Language": f"{cfg.locale},en;q=0.9"},
            )
            # Light stealth: mask webdriver flag the common automation-detect
            # scripts check for first. Not bulletproof, but costs nothing.
            await context.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', { get: () => false });"
            )
            yield context
        finally:
            await browser.close()


# ---- Human-ish delay + CAPTCHA helpers ────────────────────────────────────


def jitter_delay(base: float, spread: float = 0.4) -> float:
    """Return a positive-only uniform-ish delay centered on `base`.

    Exposed as a pure function so tests can pin behavior without sleeping.
    """
    low = max(0.0, base - spread)
    high = max(low, base + spread)
    return random.uniform(low, high)


async def human_pause(mean_seconds: float = 1.0, spread: float = 0.4) -> None:
    """asyncio.sleep a jittered human-ish duration."""
    await asyncio.sleep(jitter_delay(mean_seconds, spread))


CAPTCHA_SIGNATURES = (
    "captcha",
    "verify you are human",
    "unusual traffic",
    "automated queries",
    "cf-challenge",
    "cf_chl_",
    "px-captcha",
)


def looks_like_captcha(html_or_url: str) -> bool:
    """Heuristic check for CAPTCHA / anti-bot interstitials.

    Called on both the URL (after redirect) and a snippet of the body.
    """
    blob = (html_or_url or "").lower()
    return any(sig in blob for sig in CAPTCHA_SIGNATURES)


async def degrade_on_captcha(page: Page) -> bool:  # type: ignore[name-defined]
    """Return True if the current page looks like a CAPTCHA challenge.

    Scrapers check this right after `page.goto()` and abort the run rather
    than trying to solve. We'd rather miss a day than get the IP burned.
    """
    url = page.url or ""
    body = ""
    try:
        body = (await page.content())[:4096]
    except Exception:  # noqa: BLE001
        pass
    if looks_like_captcha(url) or looks_like_captcha(body):
        log.warning("scrape.captcha.detected url=%s", url)
        return True
    return False
