"""Playwright-based scrapers (spec Sprint 5 / TKT-060 → TKT-062).

These are **opt-in**: playwright is declared under `[project.optional-dependencies].browser`
and is not installed by default. Import `.harness` lazily — the module
raises a friendly `MissingBrowserDep` error if playwright isn't available.

Public scrapers:
    - `linkedin.search_public`  (no-login; degrades on CAPTCHA)
    - `indeed.search_canada`    (Cloudflare-aware, randomized delays)

Both return `list[RawPosting]` via the same DTO as the ATS clients, so the
ingest pipeline treats them identically after dedup.
"""
