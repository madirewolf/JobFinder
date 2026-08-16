"""Pre-curation fit-gate. Cheap Haiku call that decides whether to PROCEED
with curation (Sonnet) or SKIP a posting outright.

Architecture rationale (vs. bundling fit-assessment into the curation call):

  1. Tokens are wasted on bad-fit jobs if curation runs first. A Haiku
     pre-pass at ~$0.005/posting catches them before the ~$0.04 Sonnet call.

  2. Rationalization bias — a model that's just curated tends to argue the
     curation was worth doing. Splitting the gate into a separate, neutral
     call gives a more honest assessment.

The gate output lands on the `applications` row as `skipped_low_fit` /
`skip_reason` (terminal status, idempotent — `jfb draft top` won't re-pick
these on subsequent runs, so we don't pay to re-assess).

Threshold lives in code (NOT in the prompt — telling the model "the threshold
is 0.6" invites score-shopping toward the bar).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import settings
from ..llm.client import call_messages
from ..logging_config import get_logger
from .prompts import (
    build_fitgate_system_from_dir,
    build_user_message,
    parse_fitgate_response,
)
from .retrieval import (
    POSTING_CHUNKS_DEFAULT,
    SYSTEM_CHUNKS_DEFAULT,
    fetch_posting,
    top_for_posting,
    top_for_system,
)

log = get_logger(__name__)

# Conservative default: skip jobs scoring below this. Tune by editing the
# constant or via the JFB_MIN_FIT_OVERALL env var (config.py reads it).
MIN_FIT_OVERALL: float = 0.6

# Haiku 4.5 — cheap, fast, good enough for this triage decision.
DEFAULT_FITGATE_MODEL = "claude-haiku-4-5"
DEFAULT_TEMPERATURE = 0.0
DEFAULT_MAX_TOKENS = 600


@dataclass(slots=True)
class FitAssessment:
    """Structured fit-gate result. Whatever the model returned, normalised."""

    posting_id: int
    overall_score: float
    verdict: str  # 'proceed' | 'skip'
    skip_reason: str
    seniority_ok: bool
    domain_ok: bool
    raw: dict[str, Any]
    usd_cost: float
    cache_read_tokens: int


def _gate_decision(parsed: dict[str, Any], min_overall: float) -> tuple[bool, str]:
    """Decide proceed/skip from the parsed assessment + the code-side threshold.

    Returns (proceed: bool, reason: str). The model's own `verdict` is
    treated as advisory — the threshold lives in code.
    """
    score = float(parsed.get("overall_score") or 0.0)
    seniority = parsed["seniority_delta"]
    domain = parsed["domain_delta"]

    # Hard skips (regardless of score):
    if not domain.get("ok", True):
        return False, f"domain mismatch: {domain.get('reason') or 'no reason given'}"

    # Big seniority gap = skip even if score happens to clear the bar.
    if not seniority.get("ok", True):
        try:
            actual = float(seniority.get("candidate_yoe_actual") or 0)
            required = seniority.get("posting_yoe_required")
            if required is not None and float(required) - actual >= 3.0:
                return False, (
                    f"seniority gap: posting wants ~{required} yrs, candidate "
                    f"~{actual:.1f}"
                )
        except (TypeError, ValueError):
            pass

    # Score-based gate
    if score < min_overall:
        return False, parsed.get("skip_reason") or f"low fit score ({score:.2f})"

    return True, ""


async def assess_fit(
    posting_id: int,
    *,
    model: str = DEFAULT_FITGATE_MODEL,
    profile_dir: Path = Path("profile"),
    system_chunks: list | None = None,
    min_overall: float | None = None,
) -> FitAssessment:
    """Run the fit-gate against ONE posting. No curation work is done here.

    Cost: ~$0.005 Haiku cache-warmed, ~$0.013 cache-miss (first in batch).
    """
    posting = await fetch_posting(posting_id)
    if posting is None:
        raise ValueError(f"posting {posting_id} not found")

    if system_chunks is None:
        system_chunks = await top_for_system(SYSTEM_CHUNKS_DEFAULT)

    relevant = await top_for_posting(posting_id, POSTING_CHUNKS_DEFAULT)
    system = build_fitgate_system_from_dir(profile_dir, system_chunks)
    messages = build_user_message(posting, relevant)

    llm = await call_messages(
        model=model,
        operation="fitgate.haiku",
        system=system,
        messages=messages,
        max_tokens=DEFAULT_MAX_TOKENS,
        temperature=DEFAULT_TEMPERATURE,
    )

    try:
        parsed = parse_fitgate_response(llm.text)
    except Exception as e:
        # Defensive: a parse failure should NOT silently skip a posting.
        # Log the failure and return a 'proceed' verdict so the human
        # operator sees the curation result and the parse error in logs.
        log.error(
            "fitgate.parse_fail",
            posting_id=posting_id,
            error=str(e),
            text_preview=llm.text[:300],
        )
        parsed = {
            "seniority_delta": {"ok": True, "candidate_yoe_actual": 0,
                                "posting_yoe_required": None,
                                "reason": "parse failure — proceeding by default"},
            "domain_delta": {"ok": True, "candidate_strongest_domains": [],
                             "posting_required_domain": "",
                             "reason": "parse failure — proceeding by default"},
            "overall_score": float(min_overall if min_overall is not None else MIN_FIT_OVERALL),
            "verdict": "proceed",
            "skip_reason": "",
        }

    threshold = min_overall if min_overall is not None else MIN_FIT_OVERALL
    proceed, reason = _gate_decision(parsed, threshold)
    final_verdict = "proceed" if proceed else "skip"

    log.info(
        "fitgate.done",
        posting_id=posting_id,
        verdict=final_verdict,
        score=round(parsed["overall_score"], 3),
        seniority_ok=parsed["seniority_delta"]["ok"],
        domain_ok=parsed["domain_delta"]["ok"],
        skip_reason=reason if not proceed else None,
        usd=round(llm.usd_cost, 6),
        cache_read=llm.cache_read_tokens,
    )

    return FitAssessment(
        posting_id=posting_id,
        overall_score=parsed["overall_score"],
        verdict=final_verdict,
        skip_reason=reason if not proceed else "",
        seniority_ok=parsed["seniority_delta"]["ok"],
        domain_ok=parsed["domain_delta"]["ok"],
        raw=parsed,
        usd_cost=llm.usd_cost,
        cache_read_tokens=llm.cache_read_tokens,
    )
