"""Digest-rendering tests. No DB, no Resend — pure data shaping.

The `build_digest()` helper hits Postgres, so we skip it here and hand-build
`DigestData` fixtures instead. Everything tested is deterministic and
network-free.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from job_finder.notify.digest import (
    DigestData,
    render_html,
    render_subject,
    render_text,
)

UTC = timezone.utc


def _sample_top(n: int = 2) -> list[dict]:
    rows: list[dict] = []
    for i in range(n):
        rows.append(
            {
                "id": 100 + i,
                "title": f"Senior ML Engineer {i}",
                "url_canonical": f"https://jobs.example.com/{i}",
                "location": "Toronto, ON",
                "final_rank": 0.91 - 0.01 * i,
                "fit_score": 0.83,
                "check_risk_score": 0.2,
                "company": f"ExampleCo{i}",
                "bg_stringency": "lenient",
            }
        )
    return rows


def _sample_applied(n: int = 1) -> list[dict]:
    now = datetime(2026, 4, 23, 12, 0, tzinfo=UTC)
    return [
        {
            "id": 900 + i,
            "applied_at": now - timedelta(hours=6),
            "title": f"Research Engineer {i}",
            "url_canonical": f"https://careers.example.com/app/{i}",
            "company": f"AppliedCo{i}",
        }
        for i in range(n)
    ]


def _sample_followups(n: int = 1) -> list[dict]:
    now = datetime(2026, 4, 23, 12, 0, tzinfo=UTC)
    return [
        {
            "id": 700 + i,
            "applied_at": now - timedelta(days=10 + i),
            "title": f"Staff Engineer {i}",
            "url_canonical": f"https://follow.example.com/{i}",
            "company": f"FollowCo{i}",
        }
        for i in range(n)
    ]


def _fixture(
    *,
    top_n: int = 2,
    app_n: int = 1,
    followup_n: int = 1,
    mtd_usd: float = 4.72,
) -> DigestData:
    return DigestData(
        generated_at=datetime(2026, 4, 23, 9, 0, tzinfo=UTC),
        top_new=_sample_top(top_n),
        applications_yesterday=_sample_applied(app_n),
        followups_due=_sample_followups(followup_n),
        mtd_usd=mtd_usd,
    )


# ---- render_subject ────────────────────────────────────────────────────────


def test_subject_contains_date_iso():
    d = _fixture()
    subject = render_subject(d)
    assert "2026-04-23" in subject


def test_subject_reports_counts():
    d = _fixture(top_n=3, app_n=2, followup_n=1)
    subject = render_subject(d)
    assert "3 new" in subject
    assert "2 applied" in subject
    assert "1 to follow up" in subject


def test_subject_reports_mtd_spend():
    d = _fixture(mtd_usd=12.3456)
    subject = render_subject(d)
    # Dollar formatting: $12.35 (2dp)
    assert "$12.35" in subject


def test_subject_handles_empty_digest():
    d = DigestData(generated_at=datetime(2026, 4, 23, tzinfo=UTC))
    subject = render_subject(d)
    assert "0 new" in subject
    assert "0 applied" in subject
    assert "0 to follow up" in subject
    assert "$0.00" in subject


# ---- render_text ───────────────────────────────────────────────────────────


def test_text_lists_top_new_in_order():
    d = _fixture(top_n=2)
    out = render_text(d)
    idx0 = out.find("Senior ML Engineer 0")
    idx1 = out.find("Senior ML Engineer 1")
    assert 0 <= idx0 < idx1  # order preserved


def test_text_includes_rank_and_urls():
    d = _fixture(top_n=1)
    out = render_text(d)
    assert "0.91" in out
    assert "https://jobs.example.com/0" in out


def test_text_shows_none_for_empty_applied():
    d = _fixture(app_n=0)
    out = render_text(d)
    # The "Applied yesterday" section should explicitly say none.
    applied_idx = out.index("Applied yesterday:")
    tail = out[applied_idx:]
    assert "(none)" in tail


def test_text_shows_followup_ages():
    d = _fixture(followup_n=2)
    out = render_text(d)
    # Fixture: generated_at = 09:00 UTC, follow-ups applied_at = 12:00 UTC
    # `timedelta.days` truncates toward zero → 9d and 10d respectively.
    assert "9d" in out
    assert "10d" in out


def test_text_reports_mtd_spend():
    d = _fixture(mtd_usd=3.50)
    out = render_text(d)
    assert "MTD API spend: $3.50" in out


# ---- render_html ───────────────────────────────────────────────────────────


def test_html_wraps_urls_in_anchor_tags():
    d = _fixture(top_n=1)
    html = render_html(d)
    assert '<a href="https://jobs.example.com/0">' in html
    assert "Senior ML Engineer 0</a>" in html


def test_html_includes_bg_stringency_badge():
    d = _fixture(top_n=1)
    html = render_html(d)
    assert "[lenient]" in html


def test_html_italic_empty_state_for_no_top():
    d = _fixture(top_n=0, app_n=0, followup_n=0)
    html = render_html(d)
    # Empty top-new block renders an italic hint
    assert "<i>None yet" in html
    # Empty applied block renders a simple "None" hint
    assert "<i>None.</i>" in html


def test_html_footer_states_consent_policy():
    d = _fixture()
    html = render_html(d)
    # The "bot drafts, human submits" consent reminder (SPEC §0) must be in
    # every digest so future-me doesn't forget why there's no auto-submit.
    assert "Bot drafts" in html or "bot drafts" in html.lower()


def test_html_lists_generated_date():
    d = _fixture()
    html = render_html(d)
    assert "2026-04-23" in html


# ---- cross-rendering sanity ────────────────────────────────────────────────


def test_subject_and_html_and_text_agree_on_counts():
    d = _fixture(top_n=4, app_n=2, followup_n=3)
    subject = render_subject(d)
    html = render_html(d)
    text = render_text(d)
    assert "4 new" in subject
    assert "Top 4 new postings" in html
    assert "Top 4 new postings" in text


def test_render_text_is_deterministic():
    d1 = _fixture()
    d2 = _fixture()
    assert render_text(d1) == render_text(d2)


def test_render_html_is_deterministic():
    d1 = _fixture()
    d2 = _fixture()
    assert render_html(d1) == render_html(d2)


def test_digestdata_defaults_empty_lists():
    d = DigestData(generated_at=datetime(2026, 4, 23, tzinfo=UTC))
    assert d.top_new == []
    assert d.applications_yesterday == []
    assert d.followups_due == []
    assert d.mtd_usd == 0.0


def test_empty_digest_renders_without_error():
    d = DigestData(generated_at=datetime(2026, 4, 23, tzinfo=UTC))
    # Must produce valid, non-empty output even on a cold day.
    assert render_subject(d)
    assert render_text(d)
    assert render_html(d)


def test_followups_render_shows_company_and_title():
    d = _fixture(top_n=0, app_n=0, followup_n=1)
    text = render_text(d)
    html = render_html(d)
    assert "FollowCo0" in text
    assert "FollowCo0" in html
    assert "Staff Engineer 0" in text
    assert "Staff Engineer 0" in html


@pytest.mark.parametrize("mtd", [0.0, 0.99, 1.0, 9.99, 100.5, 1234.5678])
def test_subject_mtd_always_two_decimals(mtd: float):
    d = _fixture(mtd_usd=mtd)
    subject = render_subject(d)
    # Crude: always two digits after the dot, prefixed by $.
    import re

    m = re.search(r"\$(\d+)\.(\d{2})\b", subject)
    assert m is not None, subject
