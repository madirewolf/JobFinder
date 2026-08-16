"""Stage-2 classifier: pure keyword/regex pass (no LLM, no embeddings).

This runs against every ingested posting. It produces:
  - strict_hits / lenient_hits / fit_hits / anti_hits (which keywords matched)
  - a preliminary check_risk_score in [0, 1]
  - a preliminary fit_score in [0, 1]
  - a preliminary role_category

Stage 3 (embeddings) and Stage 4 (Haiku) refine these later. Everything here
runs in a few milliseconds per posting, for free.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from functools import lru_cache

from .keywords import (
    ANTI_KEYWORDS,
    FIT_KEYWORDS,
    LENIENT_KEYWORDS,
    ROLE_CATEGORY_KEYWORDS,
    STRICT_KEYWORDS,
)


@dataclass(slots=True)
class RegexResult:
    """Output of one regex pass. All hits are {phrase: count}."""

    strict_hits: dict[str, int] = field(default_factory=dict)
    lenient_hits: dict[str, int] = field(default_factory=dict)
    fit_hits: dict[str, int] = field(default_factory=dict)
    anti_hits: dict[str, int] = field(default_factory=dict)
    check_risk_score: float = 0.0
    fit_score: float = 0.0
    role_category: str = "other"


def _compile_one(phrase: str) -> re.Pattern:
    escaped = re.escape(phrase.strip())
    left = r"\b" if phrase[0].isalnum() else ""
    right = r"\b" if phrase[-1].isalnum() else ""
    return re.compile(f"{left}{escaped}{right}", re.IGNORECASE)


@lru_cache(maxsize=1)
def _compile_patterns() -> dict[str, re.Pattern]:
    """One compiled pattern per keyword across all dictionaries.

    Phrases that already end in a space or special char are matched literally;
    others get \\b boundaries to avoid substring false-positives.
    """
    patterns: dict[str, re.Pattern] = {}
    seen: set[str] = set()
    for bag in (STRICT_KEYWORDS, LENIENT_KEYWORDS, FIT_KEYWORDS, ANTI_KEYWORDS):
        for phrase in bag:
            if phrase in seen:
                continue
            seen.add(phrase)
            patterns[phrase] = _compile_one(phrase)
    return patterns


@lru_cache(maxsize=1)
def _compile_role_category_patterns() -> dict[str, list[re.Pattern]]:
    """Per-category pre-compiled patterns. Word-boundary matching matters here:
    short keys like 'ros' / 'vio' / 'mpc' would otherwise substring-match
    'previous', 'various', 'imprint' etc. and pollute role_category.
    """
    out: dict[str, list[re.Pattern]] = {}
    for cat, phrases in ROLE_CATEGORY_KEYWORDS.items():
        out[cat] = [_compile_one(p) for p in phrases]
    return out


def _count_hits(text: str, bag: dict[str, float], patterns: dict[str, re.Pattern]) -> dict[str, int]:
    """Return {phrase: occurrence_count} for every phrase in `bag` that matches."""
    out: dict[str, int] = {}
    for phrase in bag:
        n = len(patterns[phrase].findall(text))
        if n:
            out[phrase] = n
    return out


def classify(title: str, description_text: str) -> RegexResult:
    """Run keyword pass against title + description."""
    text = f"{title}\n{description_text}"
    patterns = _compile_patterns()
    out = RegexResult(
        strict_hits=_count_hits(text, STRICT_KEYWORDS, patterns),
        lenient_hits=_count_hits(text, LENIENT_KEYWORDS, patterns),
        fit_hits=_count_hits(text, FIT_KEYWORDS, patterns),
        anti_hits=_count_hits(text, ANTI_KEYWORDS, patterns),
    )
    out.check_risk_score = _check_risk(out)
    out.fit_score = _fit_score(out)
    out.role_category = _role_category(text)
    return out


def _check_risk(r: RegexResult) -> float:
    """Combine strict - lenient into a 0..1 score, diminishing returns."""
    strict_raw = sum(STRICT_KEYWORDS[p] for p in r.strict_hits)
    lenient_raw = sum(LENIENT_KEYWORDS[p] for p in r.lenient_hits)

    # Saturating curve: single 1.0 strict hit ≈ 0.63, 3× ≈ 0.86
    strict_saturated = 1.0 - math.exp(-strict_raw)
    lenient_saturated = 1.0 - math.exp(-lenient_raw * 0.7)

    score = max(0.0, min(1.0, strict_saturated - 0.4 * lenient_saturated))
    return round(score, 4)


def _fit_score(r: RegexResult) -> float:
    """Combine fit - anti into a 0..1 score."""
    fit_raw = sum(FIT_KEYWORDS[p] * min(r.fit_hits[p], 3) for p in r.fit_hits)
    anti_raw = sum(ANTI_KEYWORDS[p] * min(r.anti_hits[p], 3) for p in r.anti_hits)

    # Fit tops out around 10 weighted points
    fit_saturated = 1.0 - math.exp(-fit_raw / 6.0)
    penalty = min(1.0, anti_raw / 6.0)
    score = max(0.0, min(1.0, fit_saturated - 0.5 * penalty))
    return round(score, 4)


def _role_category(text: str) -> str:
    """First-match-wins by total word-boundary hits across each category.

    Categories iterate in dict order (Python 3.7+ preserves insertion order),
    so the higher-priority categories in keywords.py — applied_ai, ai_tooling,
    autonomy_robotics, defence_dual_use, ml_systems — get first chance to win
    on tied hit counts, biasing the classifier toward the operator's ICP.
    """
    cat_patterns = _compile_role_category_patterns()
    best_cat, best_score = "other", 0
    for cat, patterns in cat_patterns.items():
        score = sum(len(p.findall(text)) for p in patterns)
        if score > best_score:
            best_score, best_cat = score, cat
    return best_cat
