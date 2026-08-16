"""Prompt assembly for the per-application drafter.

Two drafting modes live side-by-side:

  TAILOR mode (the original):
      The model paraphrases your master bullets to match the posting's
      terminology. Outputs `tailored_bullets` — fresh prose, may rewrite
      numbers, may drift in tone. Highest keyword-match per posting,
      highest fabrication risk.

  CURATE mode (new):
      The model NEVER rewrites your master. It only:
        - selects which projects to include / drop on this posting
        - pulls VERBATIM emphasis quotes from your master files
        - optionally proposes new phrasings, clearly tagged for review
      Cover letter, talking points, and red flags are still LLM-written.
      Lowest fabrication risk — what's on your résumé is exactly what you
      wrote in profile/.

Anthropic prompt caching rules the design: everything before the <posting>
section must be byte-identical across calls in the same mode, so we never
interpolate posting-specific strings into the system block. The cached
prefix differs between tailor and curate mode (different rules + schema),
so a batch should be split by mode for cache wins.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Literal

from .types import PortfolioChunk

DraftMode = Literal["tailor", "curate"]
DRAFT_MODES: tuple[DraftMode, ...] = ("tailor", "curate")

# Canonical Skills category labels — must match the master's `**<Label>**`
# bold headings exactly. Used by the curate prompt as the controlled
# vocabulary for skills_order.
SKILLS_CATEGORIES: tuple[str, ...] = (
    "Languages",
    "Robotics, Autonomy & Control",
    "AI / ML",
    "Backend & Infrastructure",
    "Web & Frontend",
    "Mobile / Embedded / Systems",
    "Defence & Compliance Posture",
    "Trading & Quant",
    "Tooling",
)

MAX_DESCRIPTION_CHARS = 8000  # hard ceiling so pathologic postings don't blow up tokens


# ─────────────────────────────────────────────────────────────────────────────
# TAILOR MODE — original prompts. DO NOT EDIT without considering cache impact;
# any change to these strings invalidates every cached prefix.
# ─────────────────────────────────────────────────────────────────────────────

TAILOR_PERSONA = (
    "You are drafting a tailored application package for a single job posting.\n"
    "The candidate is an experienced software engineer. You will be given:\n"
    "  - the candidate's master resume\n"
    "  - the top 40 chunks from the candidate's portfolio (stable across calls)\n"
    "  - writing rules the draft must obey\n"
    "  - an output schema the response must match exactly\n"
    "Then, as a user message, you receive one job posting and the 8 portfolio\n"
    "chunks most relevant to it (via cosine similarity).\n"
    "Respond with a single JSON object matching the schema. No prose. No fences."
)

TAILOR_WRITING_RULES = (
    "<writing_rules>\n"
    "- Quantify outcomes. If no number is available, do NOT invent one.\n"
    "- First paragraph of the cover letter: one concrete, product-specific\n"
    "  sentence that proves you read THIS posting (not a generic opener).\n"
    "- Cover letter maximum: 150 words. Tight is better than long.\n"
    "- Never apologize, never mention gaps in employment, never volunteer\n"
    "  personal information (age, citizenship, background-check history).\n"
    "- Match the terminology the posting uses (e.g. if they write 'RTL'\n"
    "  don't say 'FPGA design').\n"
    "- tailored_bullets: 3–6 rewrites drawn from candidate experience/projects,\n"
    "  each phrased to match the posting's priorities.\n"
    "- talking_points: 3 short items the candidate can open interview chat with.\n"
    "- red_flags: things in the posting that might not fit the candidate\n"
    "  (tech-stack mismatch, seniority mismatch, clearance requirement, etc.).\n"
    "- suggested_resume_variant: one of web|graphics|systems_5g|ml_graphics|generic.\n"
    "</writing_rules>"
)

TAILOR_OUTPUT_SCHEMA = (
    "<output_schema>\n"
    "{\n"
    '  "tailored_bullets": [{"section":"Experience"|"Projects","bullet":"..."}],\n'
    '  "cover_letter": "string (<=150 words)",\n'
    '  "talking_points": ["string","string","string"],\n'
    '  "red_flags": ["string", "..."],\n'
    '  "suggested_resume_variant": "web"|"graphics"|"systems_5g"|"ml_graphics"|"generic"\n'
    "}\n"
    "</output_schema>"
)


# ─────────────────────────────────────────────────────────────────────────────
# CURATE MODE — selection-only. No paraphrasing. Quotes verbatim from master.
# ─────────────────────────────────────────────────────────────────────────────

CURATE_PERSONA = (
    "You are helping a software engineer SELECT — not rewrite — content from a\n"
    "hand-edited master résumé for a single job posting. The candidate has\n"
    "spent significant time wording the master themselves and does NOT want\n"
    "the master rewritten by you.\n\n"
    "A separate fit-gate has already approved this posting before you see it.\n"
    "Do NOT re-litigate fit. Your job is to produce the best curated artifact\n"
    "for a posting that has already been judged worth applying to.\n\n"
    "You will be given:\n"
    "  - the candidate's master resume (canonical truth — DO NOT REPHRASE)\n"
    "  - the top 40 chunks from the candidate's portfolio (also canonical)\n"
    "  - writing rules the draft must obey\n"
    "  - an output schema the response must match exactly\n"
    "Then, as a user message, you receive one job posting and the 8 portfolio\n"
    "chunks most relevant to it.\n\n"
    "Your job:\n"
    "  1. Rewrite the Summary section (`tailored_summary`) for THIS posting.\n"
    "     The master has a fixed 'Targeting <X> roles' closing line — DROP it.\n"
    "     The summary MUST end with a positioning statement naming what the\n"
    "     candidate BUILDS for this role-type — never a 'targeting/seeking' wish list.\n"
    "  2. Decide which project files (slugs) to include or drop. For EVERY\n"
    "     project you drop, record an entry in `angles_considered` naming the\n"
    "     alternative angle you considered before dropping (e.g. 'Bell-412\n"
    "     capstone for a build-eng role: 25k-LoC C++/CMake/ROS build\n"
    "     orchestration is directly relevant'). This forces deliberate drops\n"
    "     instead of reflex topic-match.\n"
    "  3. Reorder the Skills categories AND items within categories by\n"
    "     relevance to THIS posting. Drop categories with no relevance.\n"
    "  4. Pull 4-8 lines from the master VERBATIM as `emphasis_quotes`.\n"
    "     Each quote MUST be an exact substring of resume.md or one of\n"
    "     the project markdowns.\n"
    "  5. Optionally propose 0-3 NEW phrasings as `suggested_phrasings`,\n"
    "     clearly labelled REVIEW BEFORE USING. These are NOT silently merged.\n"
    "  6. Write a fresh cover letter, 3 talking points, and any red flags.\n\n"
    "Respond with a single JSON object matching the schema. No prose. No fences."
)

CURATE_WRITING_RULES = (
    "<writing_rules>\n"
    "## Hard rules — violations break the candidate's trust:\n"
    "- emphasis_quotes MUST be exact substrings of the candidate's master\n"
    "  files (resume.md or projects/<slug>.md). Do not paraphrase, expand,\n"
    "  truncate punctuation, or 'fix' grammar in a quote. Verbatim only.\n"
    "- DO NOT invent numbers, dates, team sizes, or technologies that are not\n"
    "  in the master. If the master says ~25,500 LoC, do not say 26K.\n"
    "- Preserve EVERY number from the master (LoC, $ amounts, durations,\n"
    "  counts) in the curated output — never round, drop, or restate them.\n"
    "- Where a master bullet states impact WITHOUT a number and one can be\n"
    "  reasonably inferred from context already in the master (silicon\n"
    "  revisions, mission profiles tested, target FPS), put the inferred-\n"
    "  number version in `suggested_phrasings` for operator review — NEVER\n"
    "  fabricate it into a quote or the summary.\n"
    "- Cover letter, talking_points, and suggested_phrasings ARE allowed to\n"
    "  use new prose, but every claim of fact must trace to the master.\n"
    "## Tailored Summary rules (4-5 line prose paragraph):\n"
    "- Mirror or closely paraphrase the posting's role title in the first\n"
    "  sentence. Don't claim a title the posting doesn't use.\n"
    "- Keep these factual claims intact: UofT 2025 grad; cGPA 3.55; Honors\n"
    "  List; ~14-month Tenstorrent internship (May 2023 - July 2024);\n"
    "  Founding Engineer at Vimy Systèmes (first engineering hire) since\n"
    "  Aug 2025; ECE496Y1 Bell-412 capstone (~25,500 LoC C++).\n"
    "- Reframe positioning per posting. For a build-engineering role, lead\n"
    "  with the build-orchestration / CI / large-codebase angle. For a\n"
    "  graphics role, lead with React Three Fiber + WebGL work.\n"
    "- HARD RULE: do NOT include a 'Targeting <X> roles' sentence anywhere in\n"
    "  the summary. The summary MUST END with a positioning statement that\n"
    "  names what the candidate BUILDS for this role-type — never what they\n"
    "  want. Wish-list closers ('targeting…', 'seeking…', 'looking for…') are\n"
    "  forbidden.\n"
    "- ONE positioning closer only. If the summary already ends with a sentence\n"
    "  naming what the candidate builds, do NOT append a second — two closers\n"
    "  that say the same thing read as padding.\n"
    "- DO NOT claim domains with no evidence in the master. No 'graphic-\n"
    "  design experience' or '5 years of distributed systems' fabrication.\n"
    "- Avoid hedging / editorializing in the summary and cover letter: no\n"
    "  'secondary contribution', no '<X>-adjacent', no 'public-facing framing\n"
    "  only' disclaimers. State the work plainly or omit it.\n"
    "## Skills ordering rules:\n"
    "- skills_order: list of category labels, most-to-least relevant for\n"
    "  THIS posting. Use these strings exactly:\n"
    "    'Languages', 'Robotics, Autonomy & Control', 'AI / ML',\n"
    "    'Backend & Infrastructure', 'Web & Frontend',\n"
    "    'Mobile / Embedded / Systems', 'Defence & Compliance Posture',\n"
    "    'Trading & Quant', 'Tooling'.\n"
    "- Categories NOT in skills_order are dropped from the rendered résumé.\n"
    "- skills_item_order: dict mapping each kept category to a list of item\n"
    "  names (verbatim from master) in priority order for this posting.\n"
    "  Items omitted from the list are dropped. It is fine to drop items\n"
    "  inside a kept category if they have no posting-relevance.\n"
    "## Project inclusion/exclusion (the angle test):\n"
    "- For EVERY project you put in `dropped_projects`, you MUST add an\n"
    "  entry to `angles_considered` recording the alternative angle you\n"
    "  considered before dropping. Example: dropping 'capstone-bell412' for\n"
    "  a build-engineering role requires recording the angle '25k-LoC\n"
    "  C++/CMake/ROS build orchestration over a year-long project'.\n"
    "- This is mandatory. The decision can still be 'drop' after considering\n"
    "  the angle, but the consideration must be recorded.\n"
    "- For projects you keep, recording an angle is optional.\n"
    "- The Bell-412 capstone (capstone-bell412) is almost ALWAYS relevant via\n"
    "  some angle: build-eng / full-stack -> 25k-LoC C++/CMake/ROS build graph\n"
    "  + Gazebo SITL test harness; AI/ML -> the OpenCV/YOLO perception\n"
    "  pipeline; robotics -> the full autonomy stack. Prefer KEEPING it with\n"
    "  the right-angle framing over dropping it.\n"
    "## Selection rules:\n"
    "- selected_projects: 3-7 slugs from projects/<slug>.md plus the literal\n"
    "  slug 'resume' (always selected). Order by relevance, most first.\n"
    "- dropped_projects: every other slug from the candidate's projects/.\n"
    "  Together selected + dropped MUST cover all project files.\n"
    "## Cover letter rules:\n"
    "- Maximum 150 words. Tight is better than long.\n"
    "- First paragraph: one concrete, product-specific sentence that proves\n"
    "  you read THIS posting (not a generic opener).\n"
    "- Never apologise, never mention gaps in employment, never volunteer\n"
    "  personal information (age, citizenship, background-check history).\n"
    "- Match the terminology the posting uses.\n"
    "## Suggested phrasings rules:\n"
    "- Each suggested_phrasing has a `rationale` (why this rewording would\n"
    "  match the posting better than the master's current language) and a\n"
    "  `suggestion` (the proposed new line). Keep both short.\n"
    "- 0 suggestions is acceptable. Do not pad.\n"
    "## Talking points / red flags / variant:\n"
    "- talking_points: 3 short items the candidate can open interview chat with.\n"
    "- red_flags: things in the posting that might not fit the candidate.\n"
    "- suggested_resume_variant: one of web|graphics|systems_5g|ml_graphics|generic.\n"
    "</writing_rules>"
)

CURATE_OUTPUT_SCHEMA = (
    "<output_schema>\n"
    "{\n"
    '  "tailored_summary": "<4-5 line prose paragraph for THIS posting>",\n'
    '  "skills_order": ["<category label>", "..."],\n'
    '  "skills_item_order": {"<category label>": ["<item>", "..."]},\n'
    '  "selected_projects": ["resume","capstone-bell412","..."],\n'
    '  "dropped_projects":  ["limiliminal","..."],\n'
    '  "angles_considered": [\n'
    '    {"slug":"<slug>", "angle":"<short reason>", "decision":"kept"|"dropped"}\n'
    "  ],\n"
    '  "emphasis_quotes": [\n'
    '    {"source":"resume.md","quote":"<exact substring>"},\n'
    '    {"source":"projects/<slug>.md","quote":"<exact substring>"}\n'
    "  ],\n"
    '  "suggested_phrasings": [\n'
    '    {"rationale":"<short>", "suggestion":"<short>"}\n'
    "  ],\n"
    '  "cover_letter": "string (<=150 words)",\n'
    '  "talking_points": ["string","string","string"],\n'
    '  "red_flags": ["string", "..."],\n'
    '  "suggested_resume_variant": "web"|"graphics"|"systems_5g"|"ml_graphics"|"generic"\n'
    "}\n"
    "</output_schema>"
)


# ─────────────────────────────────────────────────────────────────────────────
# FIT-GATE MODE — runs FIRST on Haiku, before any curation work. Produces a
# structured fit assessment; the drafter gates curation on this result.
# Splitting this from curation (a) avoids paying Sonnet to curate jobs that
# will be discarded, and (b) avoids the rationalization bias of a model that
# just curated arguing the fit was fine.
# ─────────────────────────────────────────────────────────────────────────────

FITGATE_PERSONA = (
    "You are a hiring-manager-style screener. Given a candidate's master\n"
    "résumé and ONE job posting, decide whether to PROCEED with résumé\n"
    "curation or SKIP. You will NOT do any curation work yourself. You only\n"
    "output a structured fit assessment. A separate downstream call will run\n"
    "only on rows you mark PROCEED.\n\n"
    "Be honest and conservative. Skipping a borderline job is cheap; running\n"
    "curation on a bad-fit job wastes tokens AND wastes the operator's review\n"
    "time. Do not invent angles to 'rescue' a bad fit — that's the curation\n"
    "step's job on jobs that already passed. If the role and the candidate\n"
    "don't line up on seniority OR domain, mark SKIP.\n\n"
    "Respond with a single JSON object matching the schema. No prose. No fences."
)

FITGATE_WRITING_RULES = (
    "<rules>\n"
    "## seniority_delta\n"
    "- ok=true if the posting's required years-of-experience are within ~2\n"
    "  years of the candidate's actual tenure (sum of full-time + significant\n"
    "  internship; ignore one-off side projects).\n"
    "- ok=false if the posting clearly requires substantially more — e.g.\n"
    "  'Senior' / 'Staff' / 'Principal' titles with 5+ yrs required vs the\n"
    "  candidate's ~1.5 yrs of post-undergrad time.\n"
    "- Read explicit YoE requirements from the JD. If the JD only signals\n"
    "  seniority via title, infer: Junior=0-2, Mid=2-5, Senior=5-8, Staff=8+.\n"
    "## domain_delta\n"
    "- ok=true if the posting's core required skill set falls within the\n"
    "  candidate's strongest demonstrated domains. Infer those domains from\n"
    "  the master's experience, projects, and skills sections.\n"
    "- ok=false if the role is wholly outside — e.g. graphic-design role\n"
    "  for a software engineer, recruiter role for a coder, sales role for\n"
    "  a researcher.\n"
    "- Adjacent-but-different domains (e.g. quant-trading role for a SWE\n"
    "  with a personal trading project) get ok=true with a hedged reason.\n"
    "## overall_score (0..1)\n"
    "- 0.00-0.39: clear skip\n"
    "- 0.40-0.59: weak fit, skip\n"
    "- 0.60-0.79: acceptable fit, proceed\n"
    "- 0.80-1.00: strong fit, proceed\n"
    "## verdict\n"
    "- 'skip' if the score lands in either skip band, OR seniority_delta.ok\n"
    "  is false with a 3+ year gap, OR domain_delta.ok is false.\n"
    "- 'proceed' otherwise.\n"
    "- skip_reason is REQUIRED iff verdict='skip' — one short sentence the\n"
    "  operator can read in their log.\n"
    "</rules>"
)

FITGATE_OUTPUT_SCHEMA = (
    "<output_schema>\n"
    "{\n"
    '  "seniority_delta": {\n'
    '    "ok": true,\n'
    '    "candidate_yoe_actual": 0,\n'
    '    "posting_yoe_required": 0,\n'
    '    "reason": "<one short sentence>"\n'
    "  },\n"
    '  "domain_delta": {\n'
    '    "ok": true,\n'
    '    "candidate_strongest_domains": ["<short label>"],\n'
    '    "posting_required_domain": "<short label>",\n'
    '    "reason": "<one short sentence>"\n'
    "  },\n"
    '  "overall_score": 0.0,\n'
    '  "verdict": "proceed",\n'
    '  "skip_reason": "<required iff verdict=skip>"\n'
    "}\n"
    "</output_schema>"
)


def build_fitgate_system(
    resume_text: str,
    system_chunks: list[PortfolioChunk],
) -> list[dict[str, Any]]:
    """Cacheable system block for the Haiku fit-gate.

    Same caching structure as the curate path — master + chunks are stable
    across all postings, so the prefix gets cached once and re-read for each
    subsequent posting in a batch.
    """
    body = (
        FITGATE_PERSONA
        + "\n\n"
        + "<master_resume>\n"
        + resume_text.strip()
        + "\n</master_resume>\n\n"
        + "<top_40_portfolio_chunks>\n"
        + _format_chunks(system_chunks)
        + "\n</top_40_portfolio_chunks>\n\n"
        + FITGATE_WRITING_RULES
        + "\n\n"
        + FITGATE_OUTPUT_SCHEMA
    )
    return [
        {
            "type": "text",
            "text": body,
            "cache_control": {"type": "ephemeral"},
        },
    ]


def build_fitgate_system_from_dir(
    profile_dir: Path,
    system_chunks: list[PortfolioChunk],
) -> list[dict[str, Any]]:
    return build_fitgate_system(_resume_text(profile_dir), system_chunks)


def parse_fitgate_response(text: str) -> dict[str, Any]:
    """Parse + shape-guard the fit-gate JSON. Defaults are conservative —
    a missing/malformed response treats as 'proceed' (don't accidentally
    block legitimate work) but logs the parse failure separately upstream.
    """
    obj = _extract_json(text)

    sd = obj.get("seniority_delta") or {}
    if not isinstance(sd, dict):
        sd = {}
    obj["seniority_delta"] = {
        "ok": bool(sd.get("ok", True)),
        "candidate_yoe_actual": float(sd.get("candidate_yoe_actual") or 0),
        "posting_yoe_required": (
            float(sd["posting_yoe_required"])
            if sd.get("posting_yoe_required") is not None
            else None
        ),
        "reason": str(sd.get("reason", "")),
    }

    dd = obj.get("domain_delta") or {}
    if not isinstance(dd, dict):
        dd = {}
    obj["domain_delta"] = {
        "ok": bool(dd.get("ok", True)),
        "candidate_strongest_domains": [
            str(d) for d in (dd.get("candidate_strongest_domains") or [])
            if isinstance(d, str)
        ],
        "posting_required_domain": str(dd.get("posting_required_domain", "")),
        "reason": str(dd.get("reason", "")),
    }

    try:
        obj["overall_score"] = max(0.0, min(1.0, float(obj.get("overall_score") or 0.0)))
    except (TypeError, ValueError):
        obj["overall_score"] = 0.0

    verdict = obj.get("verdict")
    obj["verdict"] = verdict if verdict in ("proceed", "skip") else "proceed"
    obj["skip_reason"] = str(obj.get("skip_reason") or "")
    return obj


# ─────────────────────────────────────────────────────────────────────────────
# Shared helpers
# ─────────────────────────────────────────────────────────────────────────────

def _resume_text(profile_dir: Path) -> str:
    p = profile_dir / "resume.md"
    if not p.exists():
        return "(no resume.md found — put a 1-page master resume at profile/resume.md)"
    return p.read_text(encoding="utf-8").strip()


def _format_chunks(chunks: list[PortfolioChunk]) -> str:
    if not chunks:
        return "(no portfolio chunks indexed yet)"
    parts: list[str] = []
    for c in chunks:
        tag = c.project or c.source
        parts.append(f"[{tag}] {c.content.strip()}")
    return "\n\n".join(parts)


def _persona(mode: DraftMode) -> str:
    return CURATE_PERSONA if mode == "curate" else TAILOR_PERSONA


def _writing_rules(mode: DraftMode) -> str:
    return CURATE_WRITING_RULES if mode == "curate" else TAILOR_WRITING_RULES


def _output_schema(mode: DraftMode) -> str:
    return CURATE_OUTPUT_SCHEMA if mode == "curate" else TAILOR_OUTPUT_SCHEMA


# ─────────────────────────────────────────────────────────────────────────────
# Public builders
# ─────────────────────────────────────────────────────────────────────────────

def build_system(
    resume_text: str,
    system_chunks: list[PortfolioChunk],
    *,
    mode: DraftMode = "tailor",
) -> list[dict[str, Any]]:
    """Build the cacheable system block. Stable text → stable cache key.

    The cached prefix differs per mode (different rules + schema). Drafter
    callers should batch by mode to keep cache hits high.
    """
    body = (
        _persona(mode)
        + "\n\n"
        + "<master_resume>\n"
        + resume_text.strip()
        + "\n</master_resume>\n\n"
        + "<top_40_portfolio_chunks>\n"
        + _format_chunks(system_chunks)
        + "\n</top_40_portfolio_chunks>\n\n"
        + _writing_rules(mode)
        + "\n\n"
        + _output_schema(mode)
    )
    return [
        {
            "type": "text",
            "text": body,
            "cache_control": {"type": "ephemeral"},
        },
    ]


def build_system_from_dir(
    profile_dir: Path,
    system_chunks: list[PortfolioChunk],
    *,
    mode: DraftMode = "tailor",
) -> list[dict[str, Any]]:
    """Convenience wrapper that reads `profile/resume.md` for you."""
    return build_system(_resume_text(profile_dir), system_chunks, mode=mode)


def build_user_message(posting: dict[str, Any], relevant_chunks: list[PortfolioChunk]) -> list[dict[str, Any]]:
    """Per-posting user content: description + top-8 cosine-retrieved chunks.

    Identical for both modes — the posting and its chunks don't change between
    tailor and curate; only the system-block instructions do.
    """
    desc = (posting.get("description_text") or "")[:MAX_DESCRIPTION_CHARS]
    posting_block = (
        "<posting>\n"
        f"  Company: {posting.get('company_name', '')}\n"
        f"  Title:   {posting.get('title', '')}\n"
        f"  Location: {posting.get('location', '—')} "
        f"(remote: {posting.get('remote_type', 'unspecified')})\n"
        f"  URL: {posting.get('url_canonical', '')}\n"
        f"  Description:\n{desc}\n"
        "</posting>"
    )
    context_block = (
        "<top_8_relevant_portfolio_chunks>\n"
        + _format_chunks(relevant_chunks)
        + "\n</top_8_relevant_portfolio_chunks>"
    )
    return [{"role": "user", "content": posting_block + "\n\n" + context_block}]


# ─────────────────────────────────────────────────────────────────────────────
# Response parsing — mode-aware
# ─────────────────────────────────────────────────────────────────────────────

_VALID_VARIANTS = {"web", "graphics", "systems_5g", "ml_graphics", "generic"}


def _extract_json(text: str) -> dict[str, Any]:
    from ..llm.parsing import extract_json_object
    return extract_json_object(text, what="drafter response")


def _parse_tailor(obj: dict[str, Any]) -> dict[str, Any]:
    required = {"tailored_bullets", "cover_letter", "talking_points", "red_flags", "suggested_resume_variant"}
    missing = required - obj.keys()
    if missing:
        raise ValueError(f"drafter response missing keys: {sorted(missing)}")
    if obj.get("suggested_resume_variant") not in _VALID_VARIANTS:
        obj["suggested_resume_variant"] = "generic"
    if not isinstance(obj["tailored_bullets"], list):
        obj["tailored_bullets"] = []
    if not isinstance(obj["talking_points"], list):
        obj["talking_points"] = []
    if not isinstance(obj["red_flags"], list):
        obj["red_flags"] = []
    if not isinstance(obj["cover_letter"], str):
        obj["cover_letter"] = ""
    return obj


def _parse_curate(obj: dict[str, Any]) -> dict[str, Any]:
    # `tailored_summary`, `skills_order`, `skills_item_order`, and
    # `angles_considered` are NEW (April 2026). Fall back to safe defaults
    # if a model response from before this change predates them — but the
    # core curation fields remain required.
    required = {
        "selected_projects", "dropped_projects",
        "emphasis_quotes", "suggested_phrasings",
        "cover_letter", "talking_points", "red_flags", "suggested_resume_variant",
    }
    missing = required - obj.keys()
    if missing:
        raise ValueError(f"drafter response missing keys: {sorted(missing)}")
    if obj.get("suggested_resume_variant") not in _VALID_VARIANTS:
        obj["suggested_resume_variant"] = "generic"

    # Shape-guard list fields
    for k in ("selected_projects", "dropped_projects", "emphasis_quotes",
              "suggested_phrasings", "talking_points", "red_flags",
              "angles_considered"):
        if not isinstance(obj.get(k), list):
            obj[k] = []

    if not isinstance(obj.get("cover_letter"), str):
        obj["cover_letter"] = ""

    # New: tailored_summary — falls back to empty string (renderer keeps
    # master Summary verbatim if absent, so this is a safe degradation).
    if not isinstance(obj.get("tailored_summary"), str):
        obj["tailored_summary"] = ""

    # New: skills_order (list[str]) and skills_item_order (dict[str, list[str]]).
    # Empty list / dict = renderer falls back to master order with the existing
    # variant filter.
    raw_order = obj.get("skills_order")
    obj["skills_order"] = [str(s) for s in raw_order if isinstance(s, str)] if isinstance(raw_order, list) else []

    raw_item_order = obj.get("skills_item_order")
    if isinstance(raw_item_order, dict):
        obj["skills_item_order"] = {
            str(k): [str(it) for it in v if isinstance(it, str)]
            for k, v in raw_item_order.items()
            if isinstance(v, list)
        }
    else:
        obj["skills_item_order"] = {}

    # emphasis_quotes shape: each item is {"source": str, "quote": str}
    obj["emphasis_quotes"] = [
        {"source": str(q.get("source", "")), "quote": str(q.get("quote", ""))}
        for q in obj["emphasis_quotes"]
        if isinstance(q, dict)
    ]
    # suggested_phrasings shape: each item is {"rationale": str, "suggestion": str}
    obj["suggested_phrasings"] = [
        {"rationale": str(s.get("rationale", "")), "suggestion": str(s.get("suggestion", ""))}
        for s in obj["suggested_phrasings"]
        if isinstance(s, dict)
    ]
    # angles_considered shape: each item is {"slug", "angle", "decision"}
    obj["angles_considered"] = [
        {
            "slug": str(a.get("slug", "")),
            "angle": str(a.get("angle", "")),
            "decision": "dropped" if a.get("decision") == "dropped" else "kept",
        }
        for a in obj["angles_considered"]
        if isinstance(a, dict)
    ]
    return obj


def parse_response(text: str, *, mode: DraftMode = "tailor") -> dict[str, Any]:
    """Parse the model's JSON. Tolerates stray whitespace or prose around it.

    Mode determines required fields:
      - tailor: cover_letter, tailored_bullets, talking_points, red_flags,
                suggested_resume_variant
      - curate: cover_letter, selected_projects, dropped_projects,
                emphasis_quotes, suggested_phrasings, talking_points,
                red_flags, suggested_resume_variant

    Raises ValueError if no JSON object is found or required keys missing.
    """
    obj = _extract_json(text)
    if mode == "curate":
        return _parse_curate(obj)
    return _parse_tailor(obj)


# Allowlist of profile files the model is permitted to cite as a quote source.
# Anything else (absolute paths, ../ traversal, weird casing, non-md) gets
# rejected before we touch the filesystem — the LLM controls this string and a
# malicious / hallucinated value could otherwise read any file the bot can.
_ALLOWED_QUOTE_SOURCE = re.compile(r"^(resume\.md|projects/[A-Za-z0-9_\-]+\.md)$")


def verify_curate_quotes(
    parsed: dict[str, Any],
    profile_dir: Path,
) -> list[dict[str, Any]]:
    """Walk `emphasis_quotes` and flag any whose text isn't a substring of
    its declared source file.

    This is the trust check for curate mode. Returned list contains one entry
    per quote that FAILED verification:
        {"source": "...", "quote": "...", "reason": "..."}

    Empty list = every quote verified verbatim. Drafter logs these but does
    not auto-redact — you decide whether to use them.

    Security: `q["source"]` comes from LLM output, so it's untrusted. We
    refuse anything outside `resume.md` or `projects/<slug>.md`, then double-
    check the resolved path is still inside `profile_dir` (defence-in-depth
    against allowlist regex bugs and Windows-specific path quirks).
    """
    bad: list[dict[str, Any]] = []
    cache: dict[str, str] = {}
    profile_root = profile_dir.resolve()
    for q in parsed.get("emphasis_quotes", []):
        src = q.get("source", "")
        quote = q.get("quote", "")
        if not src or not quote:
            bad.append({"source": src, "quote": quote, "reason": "empty source or quote"})
            continue
        if not _ALLOWED_QUOTE_SOURCE.fullmatch(src):
            bad.append({"source": src, "quote": quote, "reason": "source not in allowlist"})
            continue
        try:
            resolved = (profile_dir / src).resolve()
            if not resolved.is_relative_to(profile_root):
                bad.append({"source": src, "quote": quote, "reason": "source escapes profile dir"})
                continue
            if src not in cache:
                cache[src] = resolved.read_text(encoding="utf-8")
            if quote.strip() not in cache[src]:
                bad.append({"source": src, "quote": quote, "reason": "not found in source"})
        except FileNotFoundError:
            bad.append({"source": src, "quote": quote, "reason": "source file not found"})
    return bad
