"""Read-side queries for the tracker UI.

All return plain dicts / lists so the templates stay simple. Keep the SQL
here — routes.py should not hold query strings.
"""

from __future__ import annotations

from typing import Any

from ..db import aconn
from ..drafter.draft import _HISTORY_PREPEND_SQL  # reused: snapshot prior draft on re-queue
from ..drafter.prompts import DRAFT_MODES
from ..metrics import record as record_metric
from ..resume.presets import is_valid_preset_mode
from ..resume.render import is_preset_mode, preset_slug, read_preset_cover_letter_text

# The kanban columns, left to right. Order = visual order in the UI.
KANBAN_COLUMNS: list[str] = [
    "queued",
    "drafted",
    "ready_for_human",
    "applied",
    "acknowledged",
    "phone",
    "onsite",
    "offer",
    "rejected",
]

# Statuses that reflect REAL external state — the bot must not bump backwards
# from these. Used by `queue_for_draft` (prevent re-queue from applied) and as
# the "is this a terminal state?" set elsewhere in the UI / drafter.
PROTECTED_STATUSES: frozenset[str] = frozenset({
    "applied", "acknowledged", "phone", "onsite", "offer", "rejected", "withdrawn",
})

# Back-compat alias used in pre-simplify code; identical content.
FINAL_STATUSES = PROTECTED_STATUSES


async def pipeline_stats() -> dict[str, int]:
    """Counts that drive the homepage 'next action' CTA.

    Returns:
        ingested        — total live postings in DB
        needs_classify  — live postings without a fit_score yet (regex pass owes them)
        classified      — live postings with a fit_score
        queued          — applications.status = 'queued' (waiting for drafter)
        drafted         — applications.status = 'drafted'
        ready_for_human — applications.status = 'ready_for_human' (PDF ready to review)
        applied         — applications.status = 'applied' (human submitted on company site)
        skipped_low_fit — applications.status = 'skipped_low_fit' (fit-gate said no)
    """
    async with aconn() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT
                    count(*) FILTER (
                        WHERE p.canonical_posting_id IS NULL AND p.closed_at IS NULL
                    ) AS ingested,
                    count(*) FILTER (
                        WHERE p.canonical_posting_id IS NULL AND p.closed_at IS NULL
                          AND p.fit_score IS NULL
                    ) AS needs_classify,
                    count(*) FILTER (
                        WHERE p.canonical_posting_id IS NULL AND p.closed_at IS NULL
                          AND p.fit_score IS NOT NULL
                    ) AS classified
                FROM postings p
                """
            )
            postings = await cur.fetchone()

            await cur.execute(
                """
                SELECT
                    count(*) FILTER (WHERE status = 'queued')           AS queued,
                    count(*) FILTER (WHERE status = 'drafted')          AS drafted,
                    count(*) FILTER (WHERE status = 'ready_for_human')  AS ready_for_human,
                    count(*) FILTER (WHERE status = 'applied')          AS applied,
                    count(*) FILTER (WHERE status = 'skipped_low_fit')  AS skipped_low_fit
                FROM applications
                """
            )
            apps = await cur.fetchone()
    return {
        "ingested":        int(postings["ingested"] or 0),
        "needs_classify":  int(postings["needs_classify"] or 0),
        "classified":      int(postings["classified"] or 0),
        "queued":          int(apps["queued"] or 0),
        "drafted":         int(apps["drafted"] or 0),
        "ready_for_human": int(apps["ready_for_human"] or 0),
        "applied":         int(apps["applied"] or 0),
        "skipped_low_fit": int(apps["skipped_low_fit"] or 0),
    }


async def kanban_rows() -> dict[str, list[dict[str, Any]]]:
    """Return a dict of `status -> [application_row,...]` suitable for rendering."""
    async with aconn() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT a.id, a.status::text AS status, a.drafted_at, a.applied_at,
                       a.next_action_at,
                       p.id AS posting_id, p.title, p.url_canonical,
                       p.final_rank, p.fit_score, p.check_risk_score,
                       c.name AS company, c.hq_city, c.hq_province,
                       c.bg_check_stringency::text AS bg_stringency
                FROM applications a
                JOIN postings p ON p.id = a.posting_id
                JOIN companies c ON c.id = p.company_id
                WHERE p.canonical_posting_id IS NULL
                ORDER BY COALESCE(p.final_rank, 0) DESC
                """
            )
            rows = list(await cur.fetchall())
    grouped: dict[str, list[dict[str, Any]]] = {col: [] for col in KANBAN_COLUMNS}
    for r in rows:
        col = r["status"]
        grouped.setdefault(col, []).append(r)
    return grouped


async def posting_detail(posting_id: int) -> dict[str, Any] | None:
    async with aconn() as conn:
        async with conn.cursor() as cur:
            # Explicit columns instead of p.* — the `*_hits` JSONB and
            # `description_text` blob can run >50 KB per row and the template
            # only reads a fixed subset of fields.
            await cur.execute(
                """
                SELECT p.id, p.title, p.url_canonical,
                       p.location, p.remote_type::text AS remote_type,
                       p.description_text,
                       p.salary_min, p.salary_max, p.salary_currency,
                       p.tech_stack, p.role_category,
                       p.fit_score, p.check_risk_score, p.final_rank,
                       p.first_seen, p.last_seen, p.closed_at,
                       c.name AS company, c.hq_city, c.hq_province,
                       c.bg_check_stringency::text AS bg_stringency,
                       c.bg_check_reasoning,
                       a.id AS application_id, a.status::text AS application_status,
                       a.draft_mode, a.curate_payload,
                       a.cover_letter, a.tailored_bullets, a.talking_points, a.red_flags,
                       a.draft_history,
                       a.applied_at, a.drafted_at
                FROM postings p
                JOIN companies c ON c.id = p.company_id
                LEFT JOIN applications a ON a.posting_id = p.id
                WHERE p.id = %s
                """,
                (posting_id,),
            )
            return await cur.fetchone()


async def top_postings(limit: int = 50, *, include_dismissed: bool = False) -> list[dict[str, Any]]:
    """Top-ranked active postings across all sources, irrespective of draft status.

    Used by the `/top` route as the primary starting point of the day: the
    user scans by final_rank, not by what happens to be drafted yet.
    Dismissed postings are hidden by default; pass `include_dismissed=True`
    to surface them (used by the optional `?show_dismissed=1` query param).
    """
    where_extra = "" if include_dismissed else " AND (a.status IS NULL OR a.status != 'dismissed')"
    async with aconn() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                f"""
                SELECT p.id AS posting_id, p.title, p.url_canonical, p.location,
                       p.remote_type::text AS remote_type,
                       p.final_rank, p.fit_score, p.check_risk_score,
                       c.name AS company, c.tier,
                       c.hq_city, c.hq_province,
                       c.bg_check_stringency::text AS bg_stringency,
                       a.id AS application_id,
                       a.status::text AS application_status,
                       a.draft_mode,
                       a.drafted_at, a.applied_at
                FROM postings p
                JOIN companies c ON c.id = p.company_id
                LEFT JOIN applications a ON a.posting_id = p.id
                WHERE p.canonical_posting_id IS NULL
                  AND p.closed_at IS NULL
                  AND p.final_rank IS NOT NULL
                  {where_extra}
                ORDER BY p.final_rank DESC NULLS LAST
                LIMIT %s
                """,
                (limit,),
            )
            return list(await cur.fetchall())


async def companies_overview() -> list[dict[str, Any]]:
    async with aconn() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT c.id, c.name, c.tier, c.ats_platform::text AS ats,
                       c.bg_check_stringency::text AS bg_stringency,
                       c.hq_city, c.hq_province,
                       count(p.id) FILTER (WHERE p.canonical_posting_id IS NULL
                                           AND p.closed_at IS NULL) AS live_postings,
                       avg(p.fit_score) FILTER (WHERE p.fit_score IS NOT NULL) AS avg_fit
                FROM companies c
                LEFT JOIN postings p ON p.company_id = c.id
                WHERE c.active
                GROUP BY c.id
                ORDER BY c.tier NULLS LAST, c.name
                """
            )
            return list(await cur.fetchall())


async def metrics_overview(days: int = 14) -> dict[str, Any]:
    """Dashboard data: last-N-day metric rollups + MTD spend."""
    async with aconn() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT day, metric, total
                FROM v_daily_metrics
                WHERE day >= now() - make_interval(days => %s)
                ORDER BY day DESC, metric
                """,
                (days,),
            )
            per_day = list(await cur.fetchall())

        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT operation, model, sum(usd_cost) AS usd
                FROM llm_cost_log
                WHERE ts >= date_trunc('month', now())
                GROUP BY operation, model
                ORDER BY usd DESC
                """
            )
            mtd_by_op = list(await cur.fetchall())

        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT coalesce(sum(usd_cost), 0) AS usd
                FROM llm_cost_log
                WHERE ts >= date_trunc('month', now())
                """
            )
            row = await cur.fetchone()
            mtd_total = float(row["usd"] or 0)

    return {
        "per_day": per_day,
        "mtd_by_op": mtd_by_op,
        "mtd_total_usd": mtd_total,
    }


async def dismiss_posting(posting_id: int, *, reason: str | None = None) -> int:
    """Mark a posting as 'dismissed' — operator says no thanks.

    Different from skipped_low_fit (bot decided): this is a human override
    for postings that pass the bot's filters but are unsuitable for reasons
    the bot can't see (geo lock, visa requirement, gut feeling). Hidden
    from /top by default; reversible via re-queue.

    Refuses to dismiss postings the operator already submitted to (applied
    / acknowledged / phone / onsite / offer). Skipping that protection
    would silently lose history of an application you actually sent.
    """
    _IRREVERSIBLE = ("applied", "acknowledged", "phone", "onsite", "offer")
    async with aconn() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO applications (posting_id, status, draft_mode, skip_reason)
                VALUES (%s, 'dismissed', 'curate', %s)
                ON CONFLICT (posting_id) DO UPDATE SET
                    status = CASE
                        WHEN applications.status::text = ANY(%s)
                            THEN applications.status
                        ELSE 'dismissed'::application_status_enum
                    END,
                    skip_reason = CASE
                        WHEN applications.status::text = ANY(%s)
                            THEN applications.skip_reason
                        ELSE EXCLUDED.skip_reason
                    END,
                    updated_at = now()
                RETURNING id, status::text AS status
                """,
                (posting_id, reason, list(_IRREVERSIBLE), list(_IRREVERSIBLE)),
            )
            row = await cur.fetchone()
        await conn.commit()
    if row["status"] != "dismissed":
        raise ValueError(
            f"refusing to dismiss posting {posting_id}: application already at "
            f"status={row['status']!r}"
        )
    app_id = int(row["id"])
    await record_metric(
        "application.dismissed",
        posting_id=posting_id,
        application_id=app_id,
        reason=reason or "(none)",
    )
    return app_id


async def queue_for_draft(posting_id: int, *, mode: str = "tailor") -> int:
    """First gate of the two-gate apply flow: human asks the bot to draft this posting.

    Creates an applications row with status='queued', draft_mode=<mode> if none
    exists. If a row exists in a pre-draft state, refreshes the queue and lets
    the user change their mode choice. Does NOT bump backwards from
    'ready_for_human' / 'applied' / etc. — but if the row is at 'queued' or
    'drafted', the mode update is allowed (so you can re-queue with a different
    mode before the drafter picks it up).

    Returns the application id.
    """
    # Preset pool modes ("preset:<slug>") skip the LLM draft step entirely —
    # they attach a pre-built pool résumé and go straight to ready_for_human.
    if is_preset_mode(mode):
        return await _attach_preset(posting_id, mode=mode)

    if mode not in DRAFT_MODES:
        raise ValueError(f"invalid draft mode: {mode!r}")

    protected = list(PROTECTED_STATUSES)
    async with aconn() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO applications (posting_id, status, draft_mode)
                VALUES (%s, 'queued', %s)
                ON CONFLICT (posting_id) DO UPDATE SET
                    status = CASE
                        WHEN applications.status::text = ANY(%s)
                            THEN applications.status
                        ELSE 'queued'::application_status_enum
                    END,
                    draft_mode = CASE
                        WHEN applications.status::text = ANY(%s)
                            THEN applications.draft_mode
                        ELSE EXCLUDED.draft_mode
                    END,
                    updated_at = now()
                RETURNING id, status::text AS status
                """,
                (posting_id, mode, protected, protected),
            )
            row = await cur.fetchone()
        await conn.commit()
    app_id = int(row["id"])
    await record_metric(
        "application.queued_for_draft",
        posting_id=posting_id,
        application_id=app_id,
        mode=mode,
        result_status=row["status"],
    )
    return app_id


async def _attach_preset(posting_id: int, *, mode: str) -> int:
    """Attach a preset pool résumé to a posting — no LLM, no draft step.

    The application jumps straight to 'ready_for_human' with the pool's cover
    letter prefilled; the résumé PDF is rendered on demand from the pool file.
    Any prior LLM draft is snapshotted to draft_history before being cleared,
    so switching a posting to a preset never silently loses earlier work.

    Refuses to touch an application already in a protected (external) state.
    """
    if not is_valid_preset_mode(mode):
        raise ValueError(f"unknown preset mode: {mode!r}")
    cover = read_preset_cover_letter_text(preset_slug(mode))

    async with aconn() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT id, status::text AS status FROM applications WHERE posting_id = %s",
                (posting_id,),
            )
            existing = await cur.fetchone()
            if existing and existing["status"] in PROTECTED_STATUSES:
                raise ValueError(
                    f"application is already '{existing['status']}'; can't attach a preset"
                )

            if existing is None:
                await cur.execute(
                    """
                    INSERT INTO applications
                        (posting_id, status, draft_mode, drafted_at, cover_letter)
                    VALUES (%s, 'ready_for_human', %s, now(), %s)
                    RETURNING id, status::text AS status
                    """,
                    (posting_id, mode, cover),
                )
            else:
                await cur.execute(
                    f"""
                    UPDATE applications SET
                        {_HISTORY_PREPEND_SQL},
                        status = 'ready_for_human',
                        draft_mode = %s,
                        drafted_at = now(),
                        cover_letter = %s,
                        tailored_bullets = NULL,
                        curate_payload = NULL,
                        updated_at = now()
                    WHERE posting_id = %s
                    RETURNING id, status::text AS status
                    """,
                    (mode, cover, posting_id),
                )
            row = await cur.fetchone()
        await conn.commit()

    app_id = int(row["id"])
    await record_metric(
        "application.preset_attached",
        posting_id=posting_id,
        application_id=app_id,
        mode=mode,
        result_status=row["status"],
    )
    return app_id


async def mark_applied(posting_id: int, notes: str | None = None) -> int:
    """Transition an application to `applied`. Returns the application id.

    Creates the applications row if it doesn't exist yet (rare — usually the
    drafter creates it first). `applied_at` is set; status moves forward.
    """
    async with aconn() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO applications (posting_id, status, applied_at, tracking_notes)
                VALUES (%s, 'applied', now(), %s)
                ON CONFLICT (posting_id) DO UPDATE SET
                    status = 'applied',
                    applied_at = now(),
                    tracking_notes = COALESCE(EXCLUDED.tracking_notes, applications.tracking_notes),
                    updated_at = now()
                RETURNING id
                """,
                (posting_id, notes),
            )
            row = await cur.fetchone()
        await conn.commit()
    app_id = int(row["id"])
    await record_metric(
        "application.applied",
        posting_id=posting_id,
        application_id=app_id,
    )
    return app_id


async def set_status(application_id: int, new_status: str) -> None:
    """Generic status transition (human-triggered via the UI)."""
    if new_status not in set(KANBAN_COLUMNS) | FINAL_STATUSES:
        raise ValueError(f"invalid status: {new_status}")
    async with aconn() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                UPDATE applications SET status = %s::application_status_enum,
                       updated_at = now()
                WHERE id = %s
                """,
                (new_status, application_id),
            )
        await conn.commit()
    await record_metric(
        "application.status_changed",
        application_id=application_id,
        status=new_status,
    )


async def healthcheck() -> dict[str, Any]:
    """Simple ping of DB + presence of Anthropic key + Ollama host reachability."""
    import httpx

    from ..config import settings

    status: dict[str, Any] = {"db": False, "anthropic": False, "ollama": False}
    try:
        async with aconn() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT 1 AS ok")
                await cur.fetchone()
        status["db"] = True
    except Exception as e:  # noqa: BLE001
        status["db_error"] = str(e)

    status["anthropic"] = bool(settings.anthropic_api_key)

    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            r = await client.get(f"{settings.ollama_host}/api/tags")
            status["ollama"] = r.status_code < 500
    except Exception as e:  # noqa: BLE001
        status["ollama_error"] = str(e)

    status["ok"] = status["db"] and status["anthropic"]
    return status
