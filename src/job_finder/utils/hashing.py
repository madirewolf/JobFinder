"""Title normalization and title_company_hash for cross-source dedup.

Two postings should collide on `title_company_hash` when they are "the same job"
regardless of how LinkedIn vs Greenhouse vs Workday label them.
"""

from __future__ import annotations

import hashlib
import re

# Seniority tokens stripped from front/back of titles
SENIORITY_PREFIXES = [
    "sr.",
    "sr",
    "senior",
    "staff",
    "principal",
    "lead",
    "junior",
    "jr.",
    "jr",
    "intermediate",
    "entry level",
    "entry-level",
    "mid",
    "mid-level",
    "new grad",
    "new-grad",
]

# Locations / modifiers stripped from trailing parentheticals
STRIP_SUFFIX_RE = re.compile(
    r"\s*[\(\[\-–—]\s*"
    r"(remote|hybrid|on[- ]site|onsite|"
    r"toronto|montreal|montréal|ottawa|vancouver|canada|us|usa|united states|"
    r"contract|permanent|full[- ]time|part[- ]time|intern|co[- ]op|coop|"
    r"[a-z]{2}[-\s]+[a-z]{2,}|english|french)"
    r"\s*[\)\]]?\s*$",
    re.IGNORECASE,
)

MULTI_WS_RE = re.compile(r"\s+")


def normalize_title(title: str) -> str:
    """Lowercase, strip seniority prefix, strip location/mode suffix, collapse ws."""
    t = title.strip().lower()

    # Repeatedly strip trailing parenthetical modifiers (e.g. "SWE (Toronto) (Remote)")
    for _ in range(3):
        new = STRIP_SUFFIX_RE.sub("", t).strip(" -–—,|")
        if new == t:
            break
        t = new

    # Strip leading seniority prefixes
    for prefix in SENIORITY_PREFIXES:
        if t.startswith(prefix + " "):
            t = t[len(prefix) + 1 :]
            break

    # Remove punctuation except internal slashes/dashes that matter (C++/C/Rust)
    t = re.sub(r"[^\w\s+/.#-]", " ", t)
    t = MULTI_WS_RE.sub(" ", t).strip()
    return t


def title_company_hash(title: str, company_name: str) -> str:
    """SHA-1 of normalized title + '::' + lowercased company name.

    Used as a partial unique index for live postings. Reposts of the same role
    from the same company collide here; legitimately different roles don't.
    """
    key = f"{normalize_title(title)}::{company_name.strip().lower()}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()
