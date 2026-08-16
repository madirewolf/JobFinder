"""Stage-4 Haiku batched classifier.

Selects cos-gated candidates, batches 10 per API call, and UPDATEs each
posting with structured fields. The system prefix carries the candidate
profile and is marked `cache_control: ephemeral` so it re-bills at 0.1×
input on subsequent calls within the 1h TTL.

Gate thresholds (per spec §4.2):
    skip if cosine_similarity(posting, profile) < 0.35  AND  fit_hits < 2

We fetch both signals in the same SELECT to avoid a round-trip.

Response schema (one element per input posting, matched by `id`):
    seniority, salary:{min,max,currency}, remote_type,
    location_normalized, tech_stack[], role_category,
    fit_score, check_risk_score, rationale
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..db import aconn
from ..llm.client import call_messages
from ..logging_config import get_logger
from ..metrics import record as record_metric

log = get_logger(__name__)

HAIKU_MODEL = "claude-haiku-4-5-20251001"
BATCH_SIZE = 10
DESCRIPTION_TRUNC = 2000

# Cosine distance ≤ 0.65 ↔ similarity ≥ 0.35 (pgvector `<=>` returns distance)
MAX_COS_DIST = 0.65
MIN_FIT_HITS_FALLBACK = 2

DEFAULT_PROFILE_TEXT = (
    "UofT Computer Engineering BASc + Certificate in AI Engineering "
    "(June 2025, 3.55 GPA, Honors List). Currently Founding Engineer at "
    "Vimy Systèmes (vimy.ai) — Canadian dual-use deep-tech firm running DND "
    "IDEaS / NRC / partner-organization programs. Strongest in:\n"
    "  - Applied AI / agentic systems (RAG, prompt caching, LLM evaluation, "
    "Anthropic / Ollama, vector retrieval, human-in-the-loop tooling).\n"
    "  - Autonomy & robotics (ROS, Gazebo, LVI-SAM, OctoMap, ACADO NMPC, "
    "qpOASES, MAVLink, sensor fusion, GNSS-denied navigation; ECE496Y1 "
    "capstone delivered Bell-412 helicopter flight stack in simulation).\n"
    "  - AI-accelerator silicon-software seam (Tenstorrent qualification "
    "engineering: Wormhole/Grayskull, PCIe + on-chip-memory bring-up).\n"
    "  - Full-stack web (React 18/19, Next.js, TypeScript, Tailwind, "
    "React Three Fiber).\n"
    "  - Android (Kotlin + Jetpack Compose + Hilt + Room; shipped APK "
    "using Accessibility Service).\n"
    "Located Toronto, ON. Open to remote-Canada and remote-US. Best fits: "
    "applied-AI / autonomy-systems engineer at Series A-B robotics, "
    "defence-tech, or AI-tooling startups. Salary band $110k-$160k CAD base. "
    "Background-check posture: warn don't filter; no active GoC/US "
    "clearance currently held."
)

SYSTEM_PREFIX = (
    "You extract structured fields from tech job postings for a personal "
    "job-search tool.\nRespond with JSON only — an array named `results` — "
    "matching the schema below. No prose. No markdown fences.\n\n"
    "For each input posting, produce one object keyed by `id`:\n"
    "  - id: int (copy from input)\n"
    '  - seniority: "intern"|"junior"|"mid"|"senior"|"staff"|"principal"|"unknown"\n'
    '  - salary: {min:int|null, max:int|null, currency:"CAD"|"USD"|null}\n'
    '  - remote_type: "remote"|"hybrid"|"onsite"|"unspecified"\n'
    "  - location_normalized: e.g. \"Toronto, ON\" or \"Montreal, QC\" or \"Remote Canada\" or null\n"
    '  - tech_stack: array of normalized tokens (e.g. ["python","ros","mavlink","pytorch"])\n'
    '  - role_category: "applied_ai"|"ai_tooling"|"autonomy_robotics"|"defence_dual_use"|'
    '"ml_systems"|"ml"|"graphics"|"games"|"5g_networking"|"systems"|"backend"|"web"|'
    '"mobile"|"security"|"devops"|"other"\n'
    "  - fit_score: 0.0..1.0 based on the candidate profile.\n"
    "      Rough scale: applied-AI/agentic/RAG, autonomy/robotics/SLAM/MPC, "
    "defence-dual-use, AI-accelerator silicon-software, ML-systems → 0.7..1.0; "
    "ML/graphics/systems/backend with strong overlap → 0.4..0.7; generic "
    "web/mobile/devops/security → 0.2..0.5; pure graphic-design/marketing/"
    "PHP/WordPress/SAP → 0.0..0.2. Reward Series A-B robotics/defence-tech/"
    "AI-tooling startups; penalise generic big-org SWE I/II.\n"
    "  - check_risk_score: 0.0..1.0, higher = stricter background check likely\n"
    "  - rationale: ≤20 words\n\n"
    "Candidate profile:\n"
)


@dataclass(slots=True)
class TriageReport:
    batches: int
    classified: int
    skipped_gate: int
    errors: int


def _profile_text(profile_dir: Path) -> str:
    """Build the candidate profile blob to put in the cached system prefix.

    Prefers `profile/resume.md` + `profile/prefs.md` content; falls back to
    the hardcoded default if those files don't exist yet.
    """
    parts: list[str] = []
    for name in ("resume.md", "prefs.md", "preferences.md"):
        p = profile_dir / name
        if p.exists():
            parts.append(p.read_text(encoding="utf-8").strip())
    if not parts:
        return DEFAULT_PROFILE_TEXT
    body = "\n\n---\n\n".join(parts)
    # Keep the cached prefix reasonable; 8k chars ≈ 2k tokens is plenty
    return body[:8000]


def _build_system(profile_text: str) -> list[dict[str, Any]]:
    """System content list with ephemeral cache breakpoint after the profile."""
    return [
        {
            "type": "text",
            "text": SYSTEM_PREFIX + profile_text,
            "cache_control": {"type": "ephemeral"},
        },
    ]


async def _fetch_candidates(conn, limit: int) -> list[dict[str, Any]]:
    """Pull postings that passed the cos gate OR have strong regex fit."""
    async with conn.cursor() as cur:
        await cur.execute(
            """
            WITH primary_vec AS (
                SELECT embedding FROM profile_vectors WHERE label = 'primary' LIMIT 1
            )
            SELECT
                p.id,
                p.title,
                c.name AS company,
                p.description_text,
                (e.embedding <=> (SELECT embedding FROM primary_vec)) AS cos_dist,
                (SELECT COUNT(*)::int FROM jsonb_object_keys(COALESCE(p.fit_hits, '{}'::jsonb))) AS fit_hits_count
            FROM postings p
            JOIN companies c ON c.id = p.company_id
            JOIN posting_embeddings e ON e.posting_id = p.id
            WHERE p.llm_classified_at IS NULL
              AND p.closed_at IS NULL
              AND p.canonical_posting_id IS NULL
              AND EXISTS (SELECT 1 FROM primary_vec)
              AND (
                (e.embedding <=> (SELECT embedding FROM primary_vec)) <= %s
                OR (SELECT COUNT(*)::int FROM jsonb_object_keys(COALESCE(p.fit_hits, '{}'::jsonb))) >= %s
              )
            ORDER BY p.first_seen DESC
            LIMIT %s
            """,
            (MAX_COS_DIST, MIN_FIT_HITS_FALLBACK, limit),
        )
        return list(await cur.fetchall())


async def _mark_gated_skipped(conn) -> int:
    """Mark postings that failed the gate as classified (score 0) so we don't
    keep re-selecting them. Uses the same WHERE shape as _fetch_candidates but
    inverted."""
    async with conn.cursor() as cur:
        await cur.execute(
            """
            WITH primary_vec AS (
                SELECT embedding FROM profile_vectors WHERE label = 'primary' LIMIT 1
            )
            UPDATE postings p
            SET fit_score = COALESCE(p.fit_score, 0.0),
                check_risk_score = COALESCE(p.check_risk_score, 0.0),
                llm_classified_at = now()
            FROM posting_embeddings e, primary_vec pv
            WHERE e.posting_id = p.id
              AND p.llm_classified_at IS NULL
              AND p.closed_at IS NULL
              AND p.canonical_posting_id IS NULL
              AND (e.embedding <=> pv.embedding) > %s
              AND (SELECT COUNT(*)::int FROM jsonb_object_keys(COALESCE(p.fit_hits, '{}'::jsonb))) < %s
            """,
            (MAX_COS_DIST, MIN_FIT_HITS_FALLBACK),
        )
        return cur.rowcount or 0


def _build_user_payload(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    postings = [
        {
            "id": r["id"],
            "title": r["title"],
            "company": r["company"],
            "description_text_truncated_2000": (r["description_text"] or "")[:DESCRIPTION_TRUNC],
        }
        for r in rows
    ]
    return [
        {
            "role": "user",
            "content": (
                "Classify the following postings. Respond with JSON: "
                '{"results":[...]}.\n\n'
                + json.dumps({"postings": postings}, ensure_ascii=False)
            ),
        }
    ]


def _parse_results(text: str) -> list[dict[str, Any]]:
    """Pull the `results` array out of the response, forgiving stray prose."""
    from ..llm.parsing import extract_json_object
    obj = extract_json_object(text, what="haiku triage batch")
    results = obj.get("results")
    if not isinstance(results, list):
        raise ValueError(f"response missing 'results' array: {text[:200]!r}")
    return results


def _sanitize_seniority(v: Any) -> str | None:
    allowed = {"intern", "junior", "mid", "senior", "staff", "principal", "unknown"}
    return v if isinstance(v, str) and v in allowed else None


def _sanitize_remote(v: Any) -> str:
    allowed = {"remote", "hybrid", "onsite", "unspecified"}
    return v if isinstance(v, str) and v in allowed else "unspecified"


def _sanitize_float(v: Any) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(1.0, f))


def _sanitize_int(v: Any) -> int | None:
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


async def _apply_result(conn, posting_id: int, r: dict[str, Any]) -> None:
    salary = r.get("salary") or {}
    salary_min = _sanitize_int(salary.get("min"))
    salary_max = _sanitize_int(salary.get("max"))
    currency = salary.get("currency") if salary.get("currency") in {"CAD", "USD"} else "CAD"
    tech_stack = r.get("tech_stack") if isinstance(r.get("tech_stack"), list) else None
    role_category = r.get("role_category") if isinstance(r.get("role_category"), str) else None
    seniority = _sanitize_seniority(r.get("seniority"))
    remote_type = _sanitize_remote(r.get("remote_type"))
    location = r.get("location_normalized") if isinstance(r.get("location_normalized"), str) else None
    fit = _sanitize_float(r.get("fit_score")) or 0.0
    risk = _sanitize_float(r.get("check_risk_score")) or 0.0

    async with conn.cursor() as cur:
        await cur.execute(
            """
            UPDATE postings
            SET fit_score = %s,
                check_risk_score = %s,
                seniority = COALESCE(%s, seniority),
                salary_min = COALESCE(%s, salary_min),
                salary_max = COALESCE(%s, salary_max),
                salary_currency = COALESCE(%s, salary_currency),
                tech_stack = COALESCE(%s, tech_stack),
                role_category = COALESCE(%s, role_category),
                remote_type = %s::remote_type_enum,
                location = COALESCE(%s, location),
                llm_classified_at = now()
            WHERE id = %s
            """,
            (
                fit,
                risk,
                seniority,
                salary_min,
                salary_max,
                currency,
                tech_stack,
                role_category,
                remote_type,
                location,
                posting_id,
            ),
        )


async def triage_pending(
    *,
    batch_size: int = BATCH_SIZE,
    max_batches: int = 10,
    profile_dir: Path = Path("profile"),
) -> TriageReport:
    """Classify pending postings in batches of `batch_size`.

    Each batch is one Haiku call. Caps total work at `max_batches * batch_size`
    so a runaway backlog doesn't turn into an unbounded spend.
    """
    report = TriageReport(batches=0, classified=0, skipped_gate=0, errors=0)
    system = _build_system(_profile_text(profile_dir))

    # Mark gate failures up front so we don't keep re-querying them
    async with aconn() as conn:
        report.skipped_gate = await _mark_gated_skipped(conn)
        await conn.commit()

    for _ in range(max_batches):
        async with aconn() as conn:
            rows = await _fetch_candidates(conn, limit=batch_size)
        if not rows:
            break

        messages = _build_user_payload(rows)
        try:
            llm = await call_messages(
                model=HAIKU_MODEL,
                operation="classify.haiku",
                system=system,
                messages=messages,
                max_tokens=2000,
                temperature=0.0,
            )
            parsed = _parse_results(llm.text)
        except Exception as e:  # noqa: BLE001
            report.errors += 1
            log.error("haiku.call.fail", error=str(e), batch_size=len(rows))
            continue

        by_id = {int(r["id"]): r for r in parsed if "id" in r}

        async with aconn() as conn:
            for row in rows:
                pid = int(row["id"])
                result = by_id.get(pid)
                if result is None:
                    # Mark classified anyway so we don't reloop; zero scores.
                    async with conn.cursor() as cur:
                        await cur.execute(
                            """
                            UPDATE postings
                            SET fit_score = COALESCE(fit_score, 0.0),
                                check_risk_score = COALESCE(check_risk_score, 0.0),
                                llm_classified_at = now()
                            WHERE id = %s
                            """,
                            (pid,),
                        )
                    continue
                await _apply_result(conn, pid, result)
                report.classified += 1
            await conn.commit()

        report.batches += 1
        log.info(
            "haiku.batch.ok",
            n=len(rows),
            classified=report.classified,
            usd=round(llm.usd_cost, 6),
        )

    log.info(
        "haiku.triage.done",
        batches=report.batches,
        classified=report.classified,
        skipped_gate=report.skipped_gate,
        errors=report.errors,
    )
    await record_metric(
        "classify.haiku.done",
        batches=report.batches,
        classified=report.classified,
        skipped_gate=report.skipped_gate,
        errors=report.errors,
    )
    return report
