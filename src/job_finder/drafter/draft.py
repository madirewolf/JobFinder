"""Drafter orchestrator: one call per posting, results into `applications`.

Two drafting modes — tailor (paraphrase) and curate (selection-only). The
mode is recorded per application; the drafter routes each row through the
matching prompt assembly + parser. See `prompts.py` for both.

Typical flow:
    user clicks "Queue (tailor)" or "Queue (curate)"
    → applications row inserted with status='queued', draft_mode=<choice>
    `jfb draft top` runs:
        for mode in ('tailor', 'curate'):
            split queued rows by mode
            retrieve top-40 system chunks ONCE per mode (cache stays warm)
            for each posting in that mode-batch:
                draft_for_posting(pid, mode=mode, system_chunks=...)
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..db import aconn
from ..llm.client import call_messages
from ..logging_config import get_logger
from ..metrics import record as record_metric
from .fit_gate import MIN_FIT_OVERALL, FitAssessment, assess_fit
from .prompts import (
    DRAFT_MODES,
    DraftMode,
    build_system_from_dir,
    build_user_message,
    parse_response,
    verify_curate_quotes,
)
from .retrieval import (
    POSTING_CHUNKS_DEFAULT,
    SYSTEM_CHUNKS_DEFAULT,
    fetch_posting,
    top_for_posting,
    top_for_system,
)

log = get_logger(__name__)

SONNET = "claude-sonnet-4-6"
OPUS = "claude-opus-4-7"
DEFAULT_MODEL = SONNET
DEFAULT_TEMPERATURE = 0.3
DEFAULT_MAX_TOKENS = 4000  # was 2000 pre-2026-04-26; bumped for the new
# curate schema which adds tailored_summary, skills_order, skills_item_order,
# and angles_considered. Old cap clipped JSON mid-output.


@dataclass(slots=True)
class DraftResult:
    posting_id: int
    application_id: int
    mode: DraftMode
    model: str
    cache_read_tokens: int
    usd_cost: float
    fit_score: float | None = None
    skipped: bool = False
    skip_reason: str = ""


@dataclass(slots=True)
class BatchReport:
    drafted: int
    skipped: int
    errors: int
    total_cost_usd: float


# Cap on retained `draft_history` snapshots — protects against unbounded
# growth when a posting is re-drafted many times. Snapshots are stored
# newest-first, so we keep indices 0..(CAP-1) and drop the rest.
_HISTORY_CAP = 10

# SQL fragment that prepends the current payload to draft_history before the
# UPDATE replaces it, then trims to the most recent _HISTORY_CAP snapshots
# via jsonpath (PG 12+ feature; PG 16 in use here). Only snapshots when the
# row actually has prior draft content.
_HISTORY_PREPEND_SQL = f"""
draft_history = jsonb_path_query_array(
    CASE
        WHEN applications.cover_letter IS NOT NULL
             OR applications.tailored_bullets IS NOT NULL
             OR applications.curate_payload  IS NOT NULL
        THEN jsonb_build_array(jsonb_build_object(
                'draft_mode',       applications.draft_mode,
                'drafted_at',       applications.drafted_at,
                'cover_letter',     applications.cover_letter,
                'tailored_bullets', applications.tailored_bullets,
                'talking_points',   applications.talking_points,
                'red_flags',        applications.red_flags,
                'curate_payload',   applications.curate_payload
             )) || applications.draft_history
        ELSE applications.draft_history
    END,
    '$[0 to {_HISTORY_CAP - 1}]'
)
"""


def _curate_payload_dict(parsed: dict[str, Any]) -> dict[str, Any]:
    """Pluck the curate-mode-only fields into the JSONB payload shape."""
    return {
        # Original (Sept 2025) fields
        "selected_projects": parsed["selected_projects"],
        "dropped_projects": parsed["dropped_projects"],
        "emphasis_quotes": parsed["emphasis_quotes"],
        "suggested_phrasings": parsed["suggested_phrasings"],
        "suggested_resume_variant": parsed["suggested_resume_variant"],
        # April 2026 additions: per-posting Summary + Skills overrides + the
        # mandatory "angle considered" record for every dropped project.
        # Defaulted to safe empties by parse_response so .get() is safe.
        "tailored_summary": parsed.get("tailored_summary", ""),
        "skills_order": parsed.get("skills_order", []),
        "skills_item_order": parsed.get("skills_item_order", {}),
        "angles_considered": parsed.get("angles_considered", []),
    }


async def _upsert_skipped(
    conn,
    *,
    posting_id: int,
    mode: DraftMode,
    skip_reason: str,
    fit_score: float,
) -> int:
    """Mark a posting as `skipped_low_fit` with a reason. Terminal status —
    `jfb draft top` won't re-pick this row, so we don't pay to re-assess.
    Re-queueing via the UI explicitly resets it.
    """
    async with conn.cursor() as cur:
        await cur.execute(
            """
            INSERT INTO applications (
                posting_id, status, draft_mode, skip_reason
            )
            VALUES (%s, 'skipped_low_fit', %s, %s)
            ON CONFLICT (posting_id) DO UPDATE SET
                status = 'skipped_low_fit',
                draft_mode = EXCLUDED.draft_mode,
                skip_reason = EXCLUDED.skip_reason,
                updated_at = now()
            RETURNING id
            """,
            (posting_id, mode, skip_reason),
        )
        row = await cur.fetchone()
    return int(row["id"])


async def _upsert_application(
    conn,
    *,
    posting_id: int,
    mode: DraftMode,
    parsed: dict[str, Any],
) -> int:
    """Mode-aware upsert. One column shape; the mode chooses which fields
    carry data and which are NULL'd. Snapshots prior payload to draft_history
    (capped at _HISTORY_CAP) before replacing it.
    """
    if mode == "curate":
        bullets_jsonb = None
        curate_jsonb = json.dumps(_curate_payload_dict(parsed))
    else:
        bullets_jsonb = json.dumps(parsed["tailored_bullets"])
        curate_jsonb = None

    async with conn.cursor() as cur:
        await cur.execute(
            f"""
            INSERT INTO applications (
                posting_id, status, draft_mode, drafted_at, cover_letter,
                tailored_bullets, talking_points, red_flags, curate_payload
            )
            VALUES (%s, 'ready_for_human', %s, now(), %s,
                    %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb)
            ON CONFLICT (posting_id) DO UPDATE SET
                {_HISTORY_PREPEND_SQL},
                status = 'ready_for_human',
                draft_mode = EXCLUDED.draft_mode,
                drafted_at = now(),
                cover_letter = EXCLUDED.cover_letter,
                tailored_bullets = EXCLUDED.tailored_bullets,
                talking_points = EXCLUDED.talking_points,
                red_flags = EXCLUDED.red_flags,
                curate_payload = EXCLUDED.curate_payload,
                updated_at = now()
            RETURNING id
            """,
            (
                posting_id, mode, parsed["cover_letter"],
                bullets_jsonb,
                json.dumps(parsed["talking_points"]),
                json.dumps(parsed["red_flags"]),
                curate_jsonb,
            ),
        )
        row = await cur.fetchone()
    return int(row["id"])


async def draft_for_posting(
    posting_id: int,
    *,
    mode: DraftMode = "tailor",
    model: str = DEFAULT_MODEL,
    profile_dir: Path = Path("profile"),
    system_chunks: list | None = None,
    temperature: float = DEFAULT_TEMPERATURE,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    skip_fit_gate: bool = False,
    min_fit_overall: float | None = None,
) -> DraftResult:
    """Draft one application and persist it.

    Pipeline:
        1. Run the fit-gate (Haiku, ~$0.005) unless `skip_fit_gate=True`.
        2. If gate verdict is 'skip', mark the row `skipped_low_fit` with
           a reason and STOP — no Sonnet call, no resume PDF, terminal.
        3. Otherwise, run curation (Sonnet, ~$0.04) and persist the draft.

    `mode` selects tailor (paraphrase) or curate (selection-only) prompts.
    `system_chunks` can be passed in when batching, so callers retrieve the
    top-40 once per mode-batch instead of once per posting.
    """
    if mode not in DRAFT_MODES:
        raise ValueError(f"unknown draft mode: {mode!r}")

    posting = await fetch_posting(posting_id)
    if posting is None:
        raise ValueError(f"posting {posting_id} not found")

    if system_chunks is None:
        system_chunks = await top_for_system(SYSTEM_CHUNKS_DEFAULT)

    # ── 1. Fit-gate (Haiku) ─────────────────────────────────────────────
    fit: FitAssessment | None = None
    fit_cost = 0.0
    if not skip_fit_gate:
        fit = await assess_fit(
            posting_id,
            profile_dir=profile_dir,
            system_chunks=system_chunks,
            min_overall=min_fit_overall,
        )
        fit_cost = fit.usd_cost
        if fit.verdict == "skip":
            # ── 2. Skip path ────────────────────────────────────────────
            log.info(
                "draft.skipped_low_fit",
                posting_id=posting_id,
                score=round(fit.overall_score, 3),
                reason=fit.skip_reason,
                usd=round(fit_cost, 6),
            )
            async with aconn() as conn:
                app_id = await _upsert_skipped(
                    conn, posting_id=posting_id, mode=mode,
                    skip_reason=fit.skip_reason, fit_score=fit.overall_score,
                )
                await conn.commit()
            await record_metric(
                "draft.skipped_low_fit",
                posting_id=posting_id,
                application_id=app_id,
                mode=mode,
                fit_score=round(fit.overall_score, 3),
                reason=fit.skip_reason,
                usd_fitgate=round(fit_cost, 6),
            )
            return DraftResult(
                posting_id=posting_id, application_id=app_id, mode=mode,
                model="fitgate.haiku-only", cache_read_tokens=fit.cache_read_tokens,
                usd_cost=fit_cost, fit_score=fit.overall_score,
                skipped=True, skip_reason=fit.skip_reason,
            )

    # ── 3. Curation (Sonnet) ────────────────────────────────────────────
    relevant = await top_for_posting(posting_id, POSTING_CHUNKS_DEFAULT)
    system = build_system_from_dir(profile_dir, system_chunks, mode=mode)
    messages = build_user_message(posting, relevant)

    operation = f"draft.{mode}.sonnet" if model == SONNET else f"draft.{mode}.{model}"
    llm = await call_messages(
        model=model,
        operation=operation,
        system=system,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )

    parsed = parse_response(llm.text, mode=mode)

    # Curate mode: verify quotes are verbatim from master files. Log any
    # mismatches but do not auto-redact — the user reviews everything anyway.
    quote_violations: list[dict[str, Any]] = []
    if mode == "curate":
        quote_violations = verify_curate_quotes(parsed, profile_dir)
        if quote_violations:
            log.warning(
                "draft.curate.quote_mismatch",
                posting_id=posting_id,
                count=len(quote_violations),
                first=quote_violations[0] if quote_violations else None,
            )

    async with aconn() as conn:
        app_id = await _upsert_application(conn, posting_id=posting_id, mode=mode, parsed=parsed)
        await conn.commit()

    log.info(
        "draft.ok",
        posting_id=posting_id,
        app_id=app_id,
        mode=mode,
        model=model,
        cache_r=llm.cache_read_tokens,
        usd=round(llm.usd_cost, 6),
        variant=parsed.get("suggested_resume_variant"),
        quote_violations=len(quote_violations) if mode == "curate" else None,
    )
    total_cost = llm.usd_cost + fit_cost
    await record_metric(
        "draft.done",
        posting_id=posting_id,
        application_id=app_id,
        mode=mode,
        model=model,
        usd_curation=round(llm.usd_cost, 6),
        usd_fitgate=round(fit_cost, 6),
        usd_total=round(total_cost, 6),
        cache_read=llm.cache_read_tokens,
        variant=parsed.get("suggested_resume_variant"),
        fit_score=round(fit.overall_score, 3) if fit else None,
    )
    return DraftResult(
        posting_id=posting_id,
        application_id=app_id,
        mode=mode,
        model=model,
        cache_read_tokens=llm.cache_read_tokens,
        usd_cost=total_cost,
        fit_score=fit.overall_score if fit else None,
    )


async def _select_queued() -> list[tuple[int, DraftMode]]:
    """All queued (or already-drafted, for re-drafting) postings with their per-row mode.

    Two-gate flow (per prefs.md): user explicitly queues a posting AT a mode;
    this drafter only acts on those rows. It never auto-creates applications.
    """
    async with aconn() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT p.id AS posting_id, a.draft_mode
                FROM postings p
                JOIN applications a ON a.posting_id = p.id
                WHERE p.canonical_posting_id IS NULL
                  AND p.closed_at IS NULL
                  AND a.status IN ('queued','drafted')
                ORDER BY p.final_rank DESC NULLS LAST
                """
            )
            rows = await cur.fetchall()
    return [(int(r["posting_id"]), str(r["draft_mode"])) for r in rows]  # type: ignore[misc]


# Back-compat alias for any existing callers / tests
_select_top_unscored = _select_queued


async def draft_top(
    limit: int = 15,
    *,
    model: str = DEFAULT_MODEL,
    profile_dir: Path = Path("profile"),
    mode_filter: DraftMode | None = None,
) -> BatchReport:
    """Draft for postings the human has *queued* for drafting.

    Splits by `draft_mode` so each mode-batch shares a cached system prefix.
    `limit` caps the TOTAL batch (across modes) so a long queue doesn't blow
    up cost in one run.

    `mode_filter` (optional): if set, only draft rows queued at that mode.
    Useful for `jfb draft top --mode curate` to do just the curate batch.
    """
    pairs = await _select_queued()
    if mode_filter is not None:
        pairs = [(pid, m) for pid, m in pairs if m == mode_filter]
    pairs = pairs[:limit]
    if not pairs:
        log.info("draft.top.empty", mode_filter=mode_filter)
        return BatchReport(drafted=0, skipped=0, errors=0, total_cost_usd=0.0)

    # Bucket by mode so each cached prefix is reused within its bucket.
    by_mode: dict[DraftMode, list[int]] = defaultdict(list)
    for pid, m in pairs:
        if m in DRAFT_MODES:
            by_mode[m].append(pid)  # type: ignore[index]
        else:
            log.warning("draft.unknown_mode_skipped", posting_id=pid, mode=m)

    report = BatchReport(drafted=0, skipped=0, errors=0, total_cost_usd=0.0)
    for mode_key, ids in by_mode.items():
        if not ids:
            continue
        system_chunks = await top_for_system(SYSTEM_CHUNKS_DEFAULT)
        log.info("draft.batch.start", mode=mode_key, count=len(ids))
        for pid in ids:
            try:
                r = await draft_for_posting(
                    pid,
                    mode=mode_key,
                    model=model,
                    profile_dir=profile_dir,
                    system_chunks=system_chunks,
                )
                report.drafted += 1
                report.total_cost_usd += r.usd_cost
            except Exception as e:  # noqa: BLE001
                report.errors += 1
                log.error("draft.one.fail", posting_id=pid, mode=mode_key, error=str(e))

    log.info(
        "draft.top.done",
        drafted=report.drafted,
        errors=report.errors,
        usd=round(report.total_cost_usd, 4),
    )
    await record_metric(
        "draft.top.done",
        drafted=report.drafted,
        errors=report.errors,
        usd=round(report.total_cost_usd, 4),
    )
    return report
