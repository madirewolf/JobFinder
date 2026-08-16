"""Coroutine factories for each `/run/<action>` handler.

Kept separate from `app.py` so the web layer stays small and so each action
can import its dependencies lazily (FastAPI's startup is faster when we
don't drag the whole pipeline into module load).

Each factory returns an `async def _do(job)` that the JobRegistry will run
in a background asyncio.Task. The job receives `log_line` / `add_cost`
hooks so the live status page can show progress.
"""

from __future__ import annotations

import json
from typing import Any, Awaitable, Callable

from .jobs import Job


def build_action(slug: str) -> Callable[[Job], Awaitable[Any]]:
    if slug == "ingest":
        return _ingest
    if slug == "classify":
        return _classify
    if slug == "profile_ingest":
        return _profile_ingest
    if slug == "draft":
        return _draft
    raise KeyError(slug)


async def _ingest(job: Job) -> None:
    """Pull every seeded company on every seeded source. No LLM calls."""
    from ..ingest.orchestrator import run_all
    job.log_line("Pulling from every seeded source…")
    results_by_source = await run_all(concurrency=3)
    total_new = 0
    for source, results in (results_by_source or {}).items():
        new_in_source = sum(getattr(r, "inserted", 0) or 0 for r in results)
        updated_in_source = sum(getattr(r, "updated", 0) or 0 for r in results)
        job.log_line(
            f"  {source}: {new_in_source} new, {updated_in_source} updated "
            f"across {len(results)} company/companies"
        )
        total_new += new_in_source
    job.log_line(f"Done — {total_new} new posting(s) total.")
    job.extra["new_postings"] = total_new


async def _classify(job: Job) -> None:
    """Four-stage classification: regex → embed → Haiku → rank.
    Mirrors `jfb classify run/embed/haiku/rank` chained together.
    """
    from ..classify.embed_postings import embed_pending
    from ..classify.haiku import triage_pending
    from ..classify.rank import rank_all
    from ..classify.regex_pass import classify as regex_classify
    from ..db import aconn

    # ── Stage 1: regex (free) ─────────────────────────────────────────
    job.log_line("Stage 1/4: regex pass (free)…")
    scored = 0
    async with aconn() as c:
        async with c.cursor() as cur:
            await cur.execute(
                """
                SELECT id, title, description_text
                FROM postings
                WHERE fit_score IS NULL
                  AND canonical_posting_id IS NULL
                  AND closed_at IS NULL
                ORDER BY first_seen DESC
                LIMIT 500
                """
            )
            rows = await cur.fetchall()
        for r in rows:
            res = regex_classify(r["title"], r["description_text"])
            async with c.cursor() as cur:
                await cur.execute(
                    """
                    UPDATE postings
                    SET fit_score = %s, check_risk_score = %s,
                        role_category = %s,
                        strict_hits = %s::jsonb,
                        lenient_hits = %s::jsonb,
                        fit_hits = %s::jsonb
                    WHERE id = %s
                    """,
                    (
                        res.fit_score, res.check_risk_score, res.role_category,
                        json.dumps(res.strict_hits),
                        json.dumps(res.lenient_hits),
                        json.dumps(res.fit_hits),
                        r["id"],
                    ),
                )
            scored += 1
        await c.commit()
    job.log_line(f"  scored {scored} new posting(s) on keywords")

    # ── Stage 2: embed (free, local Ollama) ───────────────────────────
    job.log_line("Stage 2/4: embedding new postings (free, local Ollama)…")
    er = await embed_pending()
    job.log_line(f"  embedded {er.embedded} (remaining: {er.remaining})")

    # ── Stage 3: Haiku triage (paid) ──────────────────────────────────
    job.log_line("Stage 3/4: Haiku triage (~$0.01 / posting)…")
    tr = await triage_pending()
    if hasattr(tr, "usd_total"):
        job.add_cost(getattr(tr, "usd_total", 0.0) or 0.0)
    job.log_line(
        f"  triaged {tr.classified} posting(s)"
        + (f"; skipped gate: {tr.skipped_gate}" if hasattr(tr, "skipped_gate") else "")
    )

    # ── Stage 4: cosine rank (free) ───────────────────────────────────
    job.log_line("Stage 4/4: cosine rank against your profile (free)…")
    rep = await rank_all()
    ranked = getattr(rep, "scored", None) or getattr(rep, "ranked", None) or rep
    job.log_line(f"  ranked {ranked} posting(s)")
    job.extra["regex_scored"] = scored
    job.extra["haiku_classified"] = getattr(tr, "classified", 0)


async def _profile_ingest(job: Job) -> None:
    from ..classify.profile import DEFAULT_PROFILE_DIR, ingest_profile
    job.log_line("Re-chunking + re-embedding profile/*.md…")
    rep = await ingest_profile(DEFAULT_PROFILE_DIR)
    job.log_line(
        f"Done — files {rep.files_processed}, chunks {rep.chunks_inserted}, "
        f"primary centroid: {'written' if rep.aggregate_written else 'skipped'}"
    )


async def _draft(job: Job) -> None:
    from ..drafter.draft import draft_top
    job.log_line("Running fit-gate + curation on every queued posting…")
    rep = await draft_top(limit=50)
    job.add_cost(rep.total_cost_usd)
    job.log_line(
        f"Done — drafted {rep.drafted}, errors {rep.errors}, "
        f"$ {rep.total_cost_usd:.4f}"
    )
    job.extra["drafted"] = rep.drafted
    job.extra["errors"] = rep.errors
