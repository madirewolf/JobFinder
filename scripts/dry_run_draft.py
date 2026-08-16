"""Dry-run the drafter pipeline against a real posting WITHOUT spending API money.

What this exercises end-to-end:
  - top_for_system()  → cosine retrieval over profile_vectors.primary
  - top_for_posting() → cosine retrieval over the posting's embedding
  - build_system_from_dir(mode=...) → reads profile/resume.md, assembles cached prefix
  - build_user_message()    → formats the per-posting block
  - parse_response(mode=...) → validates + shape-guards the JSON
  - verify_curate_quotes()  → (curate only) checks emphasis quotes are verbatim
  - upsert path             → writes correct shape to applications.* (incl. curate_payload)

Both modes supported via --mode tailor|curate. The synthetic LLM response
matches the schema for the chosen mode.

Run with:
    uv run python scripts/dry_run_draft.py [posting_id]                 (defaults to settings.draft_mode_default)
    uv run python scripts/dry_run_draft.py [posting_id] --mode curate
    uv run python scripts/dry_run_draft.py [posting_id] --mode tailor
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Windows + psycopg async pool requires SelectorEventLoop policy.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        pass


# ───────────────────────────────────────────────────────────────────────────
# Synthetic responses, one per mode. Crafted to match the real schema shape;
# content is obviously placeholder so you can tell at a glance this wasn't a
# real draft. The curate-mode emphasis_quotes are deliberately set as actual
# substrings of resume.md so verify_curate_quotes() returns clean.
# ───────────────────────────────────────────────────────────────────────────
SYNTHETIC_TAILOR: dict[str, Any] = {
    "tailored_bullets": [
        {"section": "Experience", "bullet": "[DRY-RUN tailor] Vimy/capstone bullet — model would paraphrase to match posting stack."},
        {"section": "Experience", "bullet": "[DRY-RUN tailor] Tenstorrent qualification bullet — would target silicon/systems angle."},
        {"section": "Projects", "bullet": "[DRY-RUN tailor] gnssdeny / capstone autonomy bullet — would target robotics priorities."},
        {"section": "Projects", "bullet": "[DRY-RUN tailor] Reel_block or limiliminal bullet — would target mobile/front-end mention."},
    ],
    "cover_letter": (
        "[DRY-RUN tailor cover letter] Real cover letter would open with one concrete posting-specific sentence, "
        "then map 2-3 candidate-experience hooks to the posting's priorities, then close. ≤150 words."
    ),
    "talking_points": [
        "[DRY-RUN tailor] Opener referencing a posting-specific detail.",
        "[DRY-RUN tailor] Tie a posting requirement to a past project.",
        "[DRY-RUN tailor] A question to ask the interviewer.",
    ],
    "red_flags": [
        "[DRY-RUN tailor] Tech stack mismatch flag — would only appear if relevant.",
        "[DRY-RUN tailor] Seniority / clearance / location flag — would appear if relevant.",
    ],
    "suggested_resume_variant": "generic",
}


# These quotes are actual substrings of profile/resume.md — verify_curate_quotes
# should return [] (clean) when run against the live profile.
SYNTHETIC_CURATE: dict[str, Any] = {
    "selected_projects": [
        "resume",
        "capstone-bell412",
        "gnssdeny",
        "vimy-overview",
        "tenstorrent",
    ],
    "dropped_projects": [
        "5gcx",
        "finalfusion",
        "reel-block",
        "redline",
        "genius-activities",
        "limiliminal",
        "pokemon-dcgan",
    ],
    "emphasis_quotes": [
        {
            "source": "resume.md",
            "quote": "Computer-engineering generalist working at the seam between **autonomy, defence R&D, and applied AI**.",
        },
        {
            "source": "resume.md",
            "quote": "**Cumulative GPA: 3.55 / 4.0 · Honors List**",
        },
    ],
    "suggested_phrasings": [
        {
            "rationale": "[DRY-RUN curate] Posting names X-tech which doesn't appear verbatim in master.",
            "suggestion": "[DRY-RUN curate] Proposed new line — REVIEW BEFORE USING. Not on master.",
        },
    ],
    "cover_letter": (
        "[DRY-RUN curate cover letter] Cover letter generation is identical to tailor mode — fresh per posting, "
        "low risk, ≤150 words. Curate only changes what happens with the bullets."
    ),
    "talking_points": [
        "[DRY-RUN curate] Opener referencing a posting-specific detail.",
        "[DRY-RUN curate] Tie a posting requirement to a past project.",
        "[DRY-RUN curate] A question to ask the interviewer.",
    ],
    "red_flags": [
        "[DRY-RUN curate] Tech-stack mismatch flag if applicable.",
    ],
    "suggested_resume_variant": "generic",
}


@dataclass(slots=True)
class FakeLLMResult:
    """Mirror of llm.client.LLMResult shape, for monkey-patching purposes."""

    text: str
    model: str
    operation: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    usd_cost: float
    raw: Any


def _make_fake_call_messages(mode: str):
    """Returns a fake_call_messages closure returning the right body for the mode."""
    body = SYNTHETIC_CURATE if mode == "curate" else SYNTHETIC_TAILOR

    async def fake_call_messages(
        *,
        model: str,
        operation: str,
        system,
        messages,
        max_tokens: int = 2000,
        temperature: float = 0.0,
        log_cost: bool = True,
    ) -> FakeLLMResult:
        sys_text = system if isinstance(system, str) else "".join(b.get("text", "") for b in system)
        user_text = "\n".join(
            m["content"] if isinstance(m["content"], str) else json.dumps(m["content"])
            for m in messages
        )
        approx_in = (len(sys_text) + len(user_text)) // 4
        approx_out = len(json.dumps(body)) // 4

        return FakeLLMResult(
            text=json.dumps(body),
            model="dryrun.synthetic",
            operation=operation,
            input_tokens=approx_in,
            output_tokens=approx_out,
            cache_read_tokens=0,
            cache_write_tokens=approx_in,  # first call would write cache
            usd_cost=0.0,
            raw=None,
        )

    return fake_call_messages


async def _pick_posting_id() -> int | None:
    """Find the highest-ranked posting that's a sensible draft candidate."""
    from job_finder.db import aconn

    async with aconn() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT p.id, p.title, p.final_rank, c.name AS company,
                       a.status::text AS status
                FROM postings p
                JOIN companies c ON c.id = p.company_id
                LEFT JOIN applications a ON a.posting_id = p.id
                WHERE p.canonical_posting_id IS NULL
                  AND p.closed_at IS NULL
                  AND p.final_rank IS NOT NULL
                  AND (a.id IS NULL OR a.status NOT IN ('applied','acknowledged','phone','onsite','offer','rejected','withdrawn'))
                ORDER BY p.final_rank DESC NULLS LAST
                LIMIT 1
                """
            )
            r = await cur.fetchone()
            return int(r["id"]) if r else None


async def _capture_application(posting_id: int) -> dict[str, Any] | None:
    """Read the just-written application row so we can show what changed."""
    from job_finder.db import aconn

    async with aconn() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT id, status::text AS status, draft_mode,
                       drafted_at, applied_at,
                       length(cover_letter) AS cl_len,
                       CASE WHEN tailored_bullets IS NULL THEN 0
                            ELSE jsonb_array_length(tailored_bullets) END AS n_bullets,
                       CASE WHEN talking_points  IS NULL THEN 0
                            ELSE jsonb_array_length(talking_points)  END AS n_tp,
                       CASE WHEN red_flags       IS NULL THEN 0
                            ELSE jsonb_array_length(red_flags)       END AS n_rf,
                       CASE WHEN curate_payload IS NULL THEN NULL
                            ELSE jsonb_array_length(curate_payload->'emphasis_quotes') END AS n_quotes,
                       CASE WHEN curate_payload IS NULL THEN NULL
                            ELSE jsonb_array_length(curate_payload->'selected_projects') END AS n_selected,
                       CASE WHEN curate_payload IS NULL THEN NULL
                            ELSE jsonb_array_length(curate_payload->'dropped_projects')  END AS n_dropped,
                       CASE WHEN curate_payload IS NULL THEN NULL
                            ELSE jsonb_array_length(curate_payload->'suggested_phrasings') END AS n_suggest
                FROM applications
                WHERE posting_id = %s
                """,
                (posting_id,),
            )
            return await cur.fetchone()


async def main(posting_id_arg: int | None, mode: str) -> None:
    # Late imports so the asyncio policy override above takes effect first.
    from job_finder.config import settings
    from job_finder.drafter import draft as draft_module
    from job_finder.drafter.draft import draft_for_posting
    from job_finder.drafter.prompts import (
        build_system_from_dir,
        build_user_message,
        verify_curate_quotes,
    )
    from job_finder.drafter.retrieval import (
        POSTING_CHUNKS_DEFAULT,
        SYSTEM_CHUNKS_DEFAULT,
        fetch_posting,
        top_for_posting,
        top_for_system,
    )

    profile_dir = Path("profile")

    # 0. Resolve effective mode
    effective_mode = mode or settings.draft_mode_default
    if effective_mode not in ("tailor", "curate"):
        print(f"Bad --mode {mode!r}; expected 'tailor' or 'curate'.")
        return

    # 1. Pick a posting
    posting_id = posting_id_arg or await _pick_posting_id()
    if posting_id is None:
        print("No suitable posting found. Run `jfb ingest run` then `jfb classify rank` first.")
        return
    print(f"\n=== DRY-RUN draft for posting #{posting_id}  ·  mode={effective_mode} ===\n")

    # 2. Show the posting
    posting = await fetch_posting(posting_id)
    if posting is None:
        print(f"posting {posting_id} not found")
        return
    print(f"Title:   {posting['title']}")
    print(f"Company: {posting['company_name']}  ({posting.get('hq_city') or '—'})")
    print(f"Rank:    {posting.get('final_rank')}")
    print(f"BG:      {posting.get('bg_check_stringency')}")
    print(f"URL:     {posting.get('url_canonical')}")
    desc_preview = (posting.get("description_text") or "")[:300].replace("\n", " ")
    print(f"JD (first 300 chars): {desc_preview}…\n")

    # 3. Retrieval (mode-independent)
    print("--- retrieval ---")
    sys_chunks = await top_for_system(SYSTEM_CHUNKS_DEFAULT)
    posting_chunks = await top_for_posting(posting_id, POSTING_CHUNKS_DEFAULT)
    print(f"system chunks (top {SYSTEM_CHUNKS_DEFAULT} vs profile centroid):  {len(sys_chunks)}")
    print(f"posting chunks (top {POSTING_CHUNKS_DEFAULT} vs posting embedding): {len(posting_chunks)}")
    if not sys_chunks:
        print("  ⚠ No profile_vectors.primary row — run `jfb profile ingest` to refresh embeddings.")
    if not posting_chunks:
        print(f"  ⚠ No posting_embeddings row for posting {posting_id} — run `jfb classify rank`.")
    if posting_chunks:
        print("  closest chunk previews:")
        for c in posting_chunks[:3]:
            tag = c.project or c.source
            preview = c.content.strip().replace("\n", " ")[:100]
            print(f"    [{tag}] cos_dist={c.cos_dist:.3f}  {preview}…")
    print()

    # 4. Prompt sizes (mode-aware system block)
    print("--- prompt assembly ---")
    system = build_system_from_dir(profile_dir, sys_chunks, mode=effective_mode)
    messages = build_user_message(posting, posting_chunks)
    sys_chars = sum(len(b["text"]) for b in system)
    user_chars = sum(len(m["content"]) for m in messages)
    print(f"system block:  {sys_chars:,} chars  ≈ {sys_chars // 4:,} tokens (cached prefix, mode={effective_mode})")
    print(f"user message:  {user_chars:,} chars  ≈ {user_chars // 4:,} tokens (per-posting)")
    print(f"(Real Sonnet cost on cache-miss ≈ ${(sys_chars + user_chars) / 4 / 1e6 * 3:.4f}; "
          f"on cache-hit ≈ ${(sys_chars + user_chars) / 4 / 1e6 * 0.30:.4f})")
    print()

    # 5. Curate-mode pre-check: if dryrun would pass quote verification
    if effective_mode == "curate":
        body = SYNTHETIC_CURATE
        violations = verify_curate_quotes(body, profile_dir)
        if violations:
            print(f"--- ⚠ pre-check: {len(violations)} synthetic-quote violation(s) (only matters if testing real flow) ---")
            for v in violations[:3]:
                print(f"   {v}")
        else:
            print("--- pre-check: synthetic emphasis_quotes are verbatim substrings of master ✓ ---")
        print()

    # 6. Patch + run
    print(f"--- patching llm.client.call_messages → fake_call_messages ({effective_mode}) (no API spend) ---\n")
    real_call = draft_module.call_messages
    draft_module.call_messages = _make_fake_call_messages(effective_mode)  # type: ignore[assignment]

    try:
        result = await draft_for_posting(
            posting_id,
            mode=effective_mode,  # type: ignore[arg-type]
            model="dryrun.synthetic",
            profile_dir=profile_dir,
            system_chunks=sys_chunks,
        )
    finally:
        draft_module.call_messages = real_call

    # 7. Show the persisted state
    print("--- DraftResult ---")
    print(f"  application_id:    {result.application_id}")
    print(f"  posting_id:        {result.posting_id}")
    print(f"  mode:              {result.mode}")
    print(f"  model:             {result.model}")
    print(f"  cache_read_tokens: {result.cache_read_tokens}")
    print(f"  usd_cost (logged): ${result.usd_cost:.4f}")
    print()

    print("--- applications row after dry-run ---")
    row = await _capture_application(posting_id)
    if row:
        print(f"  id:           {row['id']}")
        print(f"  status:       {row['status']}")
        print(f"  draft_mode:   {row['draft_mode']}")
        print(f"  drafted_at:   {row['drafted_at']}")
        print(f"  applied_at:   {row['applied_at']}")
        print(f"  cover_letter: {row['cl_len']} chars")
        print(f"  talking_pts:  {row['n_tp']}")
        print(f"  red_flags:    {row['n_rf']}")
        if effective_mode == "tailor":
            print(f"  bullets:      {row['n_bullets']}     (curate_payload: NULL ✓)")
        else:
            print(f"  bullets:      {row['n_bullets']}     (NULL — curate mode ✓)")
            print(f"  selected:     {row['n_selected']}")
            print(f"  dropped:      {row['n_dropped']}")
            print(f"  emphasis_quotes:    {row['n_quotes']}")
            print(f"  suggested_phrasings:{row['n_suggest']}")
    print()

    print("=== DRY-RUN COMPLETE ===")
    print(f"Open http://127.0.0.1:8003/posting/{posting_id} to see the rendered draft.")
    print("(Server must be running: `jfb web serve --port 8003`.)")
    print()
    print("Real spend this run: $0.00 (no Anthropic call made).")


def _parse_args() -> tuple[int | None, str]:
    parser = argparse.ArgumentParser(description="Dry-run the drafter — no API spend.")
    parser.add_argument("posting_id", nargs="?", type=int, default=None,
                        help="Posting id (default: top-ranked queueable)")
    parser.add_argument("--mode", choices=["tailor", "curate"], default="",
                        help="Drafting mode (default: settings.draft_mode_default)")
    args = parser.parse_args()
    return args.posting_id, args.mode


if __name__ == "__main__":
    pid_arg, mode_arg = _parse_args()
    asyncio.run(main(pid_arg, mode_arg))
