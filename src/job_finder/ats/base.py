"""Common helpers shared across ATS clients."""

from __future__ import annotations

import re

from ..models import RemoteType

REMOTE_RE = re.compile(r"\b(remote|work from home|wfh|distributed)\b", re.IGNORECASE)
HYBRID_RE = re.compile(r"\bhybrid\b", re.IGNORECASE)
ONSITE_RE = re.compile(r"\b(on[- ]site|in[- ]office)\b", re.IGNORECASE)


def infer_remote_type(*text_sources: str | None) -> RemoteType:
    """Guess remote/hybrid/onsite from title, location, department text."""
    blob = " ".join(t for t in text_sources if t).lower()
    if not blob:
        return "unspecified"
    if HYBRID_RE.search(blob):
        return "hybrid"
    if REMOTE_RE.search(blob):
        return "remote"
    if ONSITE_RE.search(blob):
        return "onsite"
    return "unspecified"


TO_MTL_RE = re.compile(
    r"\b(toronto|montreal|montréal|mississauga|markham|vaughan|brampton|"
    r"etobicoke|scarborough|north york|laval|longueuil|quebec|québec|ottawa|"
    r"gatineau|ontario|québec|quebec|canada)\b",
    re.IGNORECASE,
)


def is_toronto_or_montreal(*text_sources: str | None) -> bool:
    blob = " ".join(t for t in text_sources if t)
    return bool(TO_MTL_RE.search(blob))
