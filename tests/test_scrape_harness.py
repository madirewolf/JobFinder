"""Tests for the Playwright-harness pure helpers and URL builders.

These don't launch a real browser — they pin:
  - jitter bounds
  - CAPTCHA signature matching
  - HarnessConfig env parsing
  - LinkedIn / Indeed search URL construction

If playwright isn't installed (the default), `managed_context()` must raise
`MissingBrowserDep` with an actionable message. We test that path too.
"""

from __future__ import annotations

import os
from urllib.parse import parse_qs, urlparse

import pytest

from job_finder.scrape.harness import (
    DEFAULT_LOCALE,
    DEFAULT_TZ,
    DEFAULT_UA,
    CAPTCHA_SIGNATURES,
    HarnessConfig,
    MissingBrowserDep,
    _ensure_playwright,
    jitter_delay,
    looks_like_captcha,
)
from job_finder.scrape.indeed import (
    build_search_url as indeed_url,
)
from job_finder.scrape.indeed import (
    SearchSpec as IndeedSpec,
)
from job_finder.scrape.linkedin import (
    build_search_url as linkedin_url,
)
from job_finder.scrape.linkedin import (
    SearchSpec as LinkedInSpec,
)


# ---- jitter_delay ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "base,spread",
    [(0.0, 0.4), (1.0, 0.4), (2.5, 1.0), (0.5, 10.0), (100.0, 0.001)],
)
def test_jitter_delay_bounded(base: float, spread: float):
    low = max(0.0, base - spread)
    high = max(low, base + spread)
    for _ in range(200):
        d = jitter_delay(base, spread)
        assert low <= d <= high
        assert d >= 0.0


def test_jitter_delay_nonnegative_when_base_zero():
    for _ in range(100):
        assert jitter_delay(0.0, 0.4) >= 0.0


def test_jitter_delay_zero_spread_is_deterministic():
    assert jitter_delay(1.5, 0.0) == 1.5


# ---- CAPTCHA detection ────────────────────────────────────────────────────


@pytest.mark.parametrize("sig", list(CAPTCHA_SIGNATURES))
def test_looks_like_captcha_matches_each_signature(sig: str):
    assert looks_like_captcha(f"blah blah {sig} blah")
    assert looks_like_captcha(sig.upper())


def test_looks_like_captcha_negative_on_normal_html():
    assert not looks_like_captcha(
        "<html><body>We are hiring a Senior ML Engineer</body></html>"
    )


def test_looks_like_captcha_handles_empty_input():
    assert not looks_like_captcha("")
    assert not looks_like_captcha(None)  # type: ignore[arg-type]


# ---- HarnessConfig ────────────────────────────────────────────────────────


def test_harness_config_defaults_from_empty_env(monkeypatch: pytest.MonkeyPatch):
    for var in (
        "SCRAPE_HEADLESS",
        "SCRAPE_SLOWMO_MS",
        "SCRAPE_UA",
        "SCRAPE_LOCALE",
        "SCRAPE_TZ",
        "PROXY_SERVER",
        "PROXY_USER",
        "PROXY_PASS",
    ):
        monkeypatch.delenv(var, raising=False)

    cfg = HarnessConfig.from_env()
    assert cfg.headless is True
    assert cfg.slow_mo_ms == 0
    assert cfg.user_agent == DEFAULT_UA
    assert cfg.locale == DEFAULT_LOCALE
    assert cfg.timezone_id == DEFAULT_TZ
    assert cfg.proxy_server is None
    assert cfg.proxy_username is None
    assert cfg.proxy_password is None


def test_harness_config_reads_proxy_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PROXY_SERVER", "http://proxy.example:3128")
    monkeypatch.setenv("PROXY_USER", "alice")
    monkeypatch.setenv("PROXY_PASS", "hunter2")

    cfg = HarnessConfig.from_env()
    assert cfg.proxy_server == "http://proxy.example:3128"
    assert cfg.proxy_username == "alice"
    assert cfg.proxy_password == "hunter2"


def test_harness_config_headless_off_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SCRAPE_HEADLESS", "0")
    assert HarnessConfig.from_env().headless is False


def test_harness_config_respects_explicit_ua(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SCRAPE_UA", "CustomBot/1.0")
    assert HarnessConfig.from_env().user_agent == "CustomBot/1.0"


# ---- MissingBrowserDep guard ──────────────────────────────────────────────


def test_ensure_playwright_raises_when_not_installed():
    """When playwright isn't available (the default in this env), the helper
    must raise a `MissingBrowserDep` whose message tells the user how to fix it.
    """
    try:
        import playwright.async_api  # noqa: F401

        pytest.skip("playwright is actually installed; this path isn't exercised")
    except ImportError:
        pass

    with pytest.raises(MissingBrowserDep) as excinfo:
        _ensure_playwright()
    msg = str(excinfo.value)
    assert "playwright" in msg.lower()
    assert "browser" in msg.lower() or "install" in msg.lower()


# ---- LinkedIn URL builder ─────────────────────────────────────────────────


def test_linkedin_url_keywords_and_location_encoded():
    u = linkedin_url(LinkedInSpec(keyword="ml engineer", location="Toronto, ON"))
    qs = parse_qs(urlparse(u).query)
    assert qs["keywords"] == ["ml engineer"]
    assert qs["location"] == ["Toronto, ON"]


def test_linkedin_url_sets_24h_filter_by_default():
    u = linkedin_url(LinkedInSpec(keyword="x", location="y"))
    qs = parse_qs(urlparse(u).query)
    assert qs["f_TPR"] == ["r86400"]


def test_linkedin_url_remote_only_toggles_f_wt():
    u_off = linkedin_url(LinkedInSpec(keyword="x", location="y", remote_only=False))
    u_on = linkedin_url(LinkedInSpec(keyword="x", location="y", remote_only=True))
    assert "f_WT" not in parse_qs(urlparse(u_off).query)
    assert parse_qs(urlparse(u_on).query)["f_WT"] == ["2"]


def test_linkedin_url_points_at_public_search():
    u = linkedin_url(LinkedInSpec(keyword="x", location="y"))
    assert urlparse(u).netloc == "www.linkedin.com"
    assert urlparse(u).path.endswith("/jobs/search")


# ---- Indeed URL builder ───────────────────────────────────────────────────


def test_indeed_url_structure():
    u = indeed_url(IndeedSpec(keyword="graphics", location="Toronto, ON"))
    p = urlparse(u)
    qs = parse_qs(p.query)
    assert p.netloc == "ca.indeed.com"
    assert qs["q"] == ["graphics"]
    assert qs["l"] == ["Toronto, ON"]
    assert qs["sort"] == ["date"]


def test_indeed_url_posted_within_days_min_one():
    u0 = indeed_url(IndeedSpec(keyword="x", location="y", posted_within_days=0))
    u1 = indeed_url(IndeedSpec(keyword="x", location="y", posted_within_days=1))
    u7 = indeed_url(IndeedSpec(keyword="x", location="y", posted_within_days=7))
    assert parse_qs(urlparse(u0).query)["fromage"] == ["1"]
    assert parse_qs(urlparse(u1).query)["fromage"] == ["1"]
    assert parse_qs(urlparse(u7).query)["fromage"] == ["7"]


def test_indeed_url_encodes_special_characters():
    u = indeed_url(IndeedSpec(keyword="c++ engineer", location="Montréal, QC"))
    # urlencode must percent-encode both the '+' and the 'é'
    assert "c%2B%2B" in u
    assert "Montr%C3%A9al" in u


# ---- Shared-locale sanity ─────────────────────────────────────────────────


def test_default_locale_is_en_ca():
    assert DEFAULT_LOCALE == "en-CA"


def test_default_timezone_is_toronto():
    assert DEFAULT_TZ == "America/Toronto"
