"""Lever v0 public postings API.

Endpoint: GET https://api.lever.co/v0/postings/{company}?mode=json

No auth. Returns array of postings with HTML `descriptionPlain`, `lists`, etc.
The `company` is the Lever site slug (e.g. "waabi", "behaviour", "neofinancial").
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..logging_config import get_logger
from ..models import RawPosting
from ..utils.canonical import canonicalize
from ..utils.html import strip_html
from ..utils.http import fetch_json, make_client
from .base import infer_remote_type

log = get_logger(__name__)

BASE_URL = "https://api.lever.co"


async def fetch(token: str) -> list[RawPosting]:
    url = f"{BASE_URL}/v0/postings/{token}?mode=json"

    async with make_client() as client:
        log.info("lever.fetch.start", token=token)
        data = await fetch_json(client, "GET", url)

    # Lever v0 returns a bare array
    assert isinstance(data, list)
    log.info("lever.fetch.ok", token=token, count=len(data))

    postings: list[RawPosting] = []
    for j in data:
        try:
            postings.append(_parse(j, token))
        except Exception as e:
            log.warning("lever.parse.fail", token=token, posting_id=j.get("id"), err=str(e))
    return postings


def _parse(j: dict[str, Any], token: str) -> RawPosting:
    # Lever fields of interest:
    #   id, text (title), hostedUrl, applyUrl, descriptionPlain, description,
    #   categories.location, categories.team, categories.commitment,
    #   workplaceType ('on-site'|'hybrid'|'remote'),
    #   createdAt (ms epoch), lists[] (requirements etc.)
    categories = j.get("categories") or {}
    location = categories.get("location")
    workplace_type = j.get("workplaceType")

    description_html = j.get("description") or ""
    # Lever also exposes descriptionPlain which is often cleaner
    desc_plain = j.get("descriptionPlain") or ""
    # Plus 'lists' (requirements, responsibilities). Concatenate for richer text.
    lists_text = "\n\n".join(
        f"{lst.get('text', '')}:\n{strip_html(lst.get('content', ''))}"
        for lst in (j.get("lists") or [])
    )
    description_text = "\n\n".join(filter(None, [desc_plain or strip_html(description_html), lists_text]))

    posted_at: datetime | None = None
    if ts := j.get("createdAt"):
        try:
            posted_at = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
        except (TypeError, ValueError):
            posted_at = None

    url_canonical = canonicalize(j.get("hostedUrl") or j.get("applyUrl") or "")

    return RawPosting(
        source="lever",
        source_rank=1,
        external_id=str(j.get("id")),
        company_name=token,
        title=str(j.get("text") or "").strip(),
        description_html=description_html,
        description_text=description_text,
        location_raw=location,
        remote_raw=workplace_type or infer_remote_type(location, str(j.get("text") or "")),
        posted_at=posted_at,
        url_canonical=url_canonical,
        raw_json=j,
    )
