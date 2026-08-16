"""Daily digest: top new postings + yesterday's applications + follow-ups + MTD spend.

Split into pure data-shaping (easy to test without Resend) and a tiny send
helper. The CLI command calls `build_digest()` then `send_digest()`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

# NOTE: `..config` and `..db` are imported lazily inside build_digest/send_digest
# so the pure `render_*` helpers (and their tests) don't drag in pydantic,
# psycopg, or settings. This keeps `tests/test_digest.py` DB/net-free.
log = logging.getLogger(__name__)

TOP_NEW_LIMIT = 15
FOLLOWUP_AFTER_DAYS = 7


@dataclass(slots=True)
class DigestData:
    generated_at: datetime
    top_new: list[dict[str, Any]] = field(default_factory=list)
    applications_yesterday: list[dict[str, Any]] = field(default_factory=list)
    followups_due: list[dict[str, Any]] = field(default_factory=list)
    mtd_usd: float = 0.0


async def build_digest(now: datetime | None = None) -> DigestData:
    """Assemble the day's digest data. Pure DB reads, no side effects."""
    from ..db import aconn  # lazy: keep DB import out of test-collection path

    now = now or datetime.now(tz=timezone.utc)
    yesterday = now - timedelta(days=1)
    followup_cutoff = now - timedelta(days=FOLLOWUP_AFTER_DAYS)

    async with aconn() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT p.id, p.title, p.url_canonical, p.location,
                       p.final_rank, p.fit_score, p.check_risk_score,
                       c.name AS company, c.bg_check_stringency::text AS bg_stringency
                FROM postings p
                JOIN companies c ON c.id = p.company_id
                WHERE p.first_seen >= %s
                  AND p.canonical_posting_id IS NULL
                  AND p.closed_at IS NULL
                  AND p.final_rank IS NOT NULL
                ORDER BY p.final_rank DESC NULLS LAST
                LIMIT %s
                """,
                (yesterday, TOP_NEW_LIMIT),
            )
            top_new = list(await cur.fetchall())

        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT a.id, a.applied_at, p.title, c.name AS company,
                       p.url_canonical
                FROM applications a
                JOIN postings p ON p.id = a.posting_id
                JOIN companies c ON c.id = p.company_id
                WHERE a.applied_at >= %s AND a.applied_at < %s
                ORDER BY a.applied_at DESC
                """,
                (yesterday, now),
            )
            applied_yesterday = list(await cur.fetchall())

        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT a.id, a.applied_at, p.title, c.name AS company,
                       p.url_canonical
                FROM applications a
                JOIN postings p ON p.id = a.posting_id
                JOIN companies c ON c.id = p.company_id
                WHERE a.status = 'applied'
                  AND a.applied_at < %s
                  AND (a.next_action_at IS NULL OR a.next_action_at <= %s)
                ORDER BY a.applied_at ASC
                """,
                (followup_cutoff, now),
            )
            followups_due = list(await cur.fetchall())

        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT COALESCE(SUM(usd_cost), 0) AS usd
                FROM llm_cost_log
                WHERE ts >= date_trunc('month', now())
                """
            )
            row = await cur.fetchone()
            mtd = float(row["usd"] or 0)

    return DigestData(
        generated_at=now,
        top_new=top_new,
        applications_yesterday=applied_yesterday,
        followups_due=followups_due,
        mtd_usd=mtd,
    )


def render_subject(d: DigestData) -> str:
    return f"[jfb] {d.generated_at.strftime('%Y-%m-%d')} · "\
           f"{len(d.top_new)} new · {len(d.applications_yesterday)} applied · "\
           f"{len(d.followups_due)} to follow up · ${d.mtd_usd:.2f} MTD"


def render_html(d: DigestData) -> str:
    """Hand-rolled minimal HTML so we don't drag Jinja into the notify package.

    Designed to be paste-legible as plain text even if the client strips HTML.
    """
    out: list[str] = []
    out.append(f"<h2>Job Finder Bot — {d.generated_at.strftime('%Y-%m-%d')}</h2>")

    out.append(f"<h3>Top {len(d.top_new)} new postings</h3>")
    if d.top_new:
        out.append("<ul>")
        for p in d.top_new:
            rank = p.get("final_rank")
            rank_s = f"{rank:.2f}" if rank is not None else "—"
            out.append(
                f'<li><b>{rank_s}</b> · {p["company"]} — '
                f'<a href="{p["url_canonical"]}">{p["title"]}</a> '
                f'<span style="color:#888">[{p.get("bg_stringency","unknown")}]</span></li>'
            )
        out.append("</ul>")
    else:
        out.append("<p><i>None yet — run an ingestion + classify pass.</i></p>")

    out.append("<h3>Applied yesterday</h3>")
    if d.applications_yesterday:
        out.append("<ul>")
        for a in d.applications_yesterday:
            out.append(
                f'<li>{a["company"]} — <a href="{a["url_canonical"]}">{a["title"]}</a></li>'
            )
        out.append("</ul>")
    else:
        out.append("<p><i>None.</i></p>")

    out.append(f"<h3>Follow-ups due ({len(d.followups_due)})</h3>")
    if d.followups_due:
        out.append("<ul>")
        for f in d.followups_due:
            days = (d.generated_at - f["applied_at"]).days
            out.append(
                f'<li>{days}d · {f["company"]} — '
                f'<a href="{f["url_canonical"]}">{f["title"]}</a></li>'
            )
        out.append("</ul>")

    out.append(f'<p style="color:#888">MTD API spend: <b>${d.mtd_usd:.2f}</b></p>')
    out.append(
        '<p style="color:#888; font-size:12px">Bot drafts; human submits. '
        "Each application still requires a conscious click in the tracker UI.</p>"
    )
    return "\n".join(out)


def render_text(d: DigestData) -> str:
    """Plaintext alternative, for clients that prefer it."""
    lines: list[str] = [
        f"Job Finder Bot — {d.generated_at.strftime('%Y-%m-%d')}",
        "",
        f"Top {len(d.top_new)} new postings:",
    ]
    for p in d.top_new:
        rank = p.get("final_rank")
        rank_s = f"{rank:.2f}" if rank is not None else "—"
        lines.append(f"  {rank_s}  {p['company']} — {p['title']}")
        lines.append(f"          {p['url_canonical']}")

    lines += ["", "Applied yesterday:"]
    if not d.applications_yesterday:
        lines.append("  (none)")
    for a in d.applications_yesterday:
        lines.append(f"  {a['company']} — {a['title']}")

    lines += ["", f"Follow-ups due ({len(d.followups_due)}):"]
    for f in d.followups_due:
        days = (d.generated_at - f["applied_at"]).days
        lines.append(f"  {days}d  {f['company']} — {f['title']}")

    lines += ["", f"MTD API spend: ${d.mtd_usd:.2f}"]
    return "\n".join(lines)


def send_digest(d: DigestData) -> dict[str, Any]:
    """Send the digest via Resend. Returns the API response dict.

    Raises RuntimeError if RESEND_API_KEY or RESEND_TO aren't configured.
    """
    from ..config import settings  # lazy: avoids pydantic on test import

    if not settings.resend_api_key:
        raise RuntimeError("RESEND_API_KEY is not set")
    if not settings.resend_to:
        raise RuntimeError("RESEND_TO is not set")

    import resend  # lazy — keeps tests for render_* DB-free and lib-free

    resend.api_key = settings.resend_api_key
    params: dict[str, Any] = {
        "from": settings.resend_from,
        "to": [settings.resend_to],
        "subject": render_subject(d),
        "html": render_html(d),
        "text": render_text(d),
    }
    resp = resend.Emails.send(params)
    log.info("digest.sent id=%s", resp.get("id") if isinstance(resp, dict) else None)
    return resp if isinstance(resp, dict) else {"raw": str(resp)}
