"""Greenhouse public board API.

Endpoint: GET https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true

No auth, no documented rate limit. Returns all open jobs with full HTML content.
The `token` is the Greenhouse board slug (e.g. "cohere", "faire", "ada").
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ..logging_config import get_logger
from ..models import RawPosting
from ..utils.canonical import canonicalize
from ..utils.html import strip_html
from ..utils.http import fetch_json, make_client
from .base import infer_remote_type

log = get_logger(__name__)

BASE_URL = "https://boards-api.greenhouse.io"


async def fetch(token: str) -> list[RawPosting]:
    """Return every live posting for the Greenhouse board `token`."""
    url = f"{BASE_URL}/v1/boards/{token}/jobs?content=true"

    async with make_client() as client:
        log.info("greenhouse.fetch.start", token=token)
        data = await fetch_json(client, "GET", url)

    assert isinstance(data, dict)
    jobs_raw: list[dict[str, Any]] = data.get("jobs") or []
    metadata = data.get("meta") or {}
    log.info("greenhouse.fetch.ok", token=token, count=len(jobs_raw), total=metadata.get("total"))

    postings: list[RawPosting] = []
    for j in jobs_raw:
        try:
            postings.append(_parse(j, token))
        except Exception as e:
            log.warning("greenhouse.parse.fail", token=token, job_id=j.get("id"), err=str(e))
    return postings


def _parse(j: dict[str, Any], token: str) -> RawPosting:
    # Greenhouse fields: id, title, absolute_url, content (HTML), location.name,
    # updated_at, departments[], offices[], metadata[]
    description_html = j.get("content") or ""
    description_text = strip_html(description_html)

    location_name = (j.get("location") or {}).get("name") or ""
    offices = ", ".join((o.get("name") or "") for o in (j.get("offices") or []))

    url_raw = j.get("absolute_url") or ""
    url_canonical = canonicalize(url_raw)

    # Greenhouse ISO-8601 timestamps
    posted_at: datetime | None = None
    if ts := j.get("updated_at"):
        try:
            posted_at = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except (TypeError, ValueError):
            posted_at = None

    return RawPosting(
        source="greenhouse",
        source_rank=1,
        external_id=str(j.get("id")),
        company_name=token,  # orchestrator will resolve to canonical company row
        title=str(j.get("title") or "").strip(),
        description_html=description_html,
        description_text=description_text,
        location_raw=location_name or offices or None,
        remote_raw=_remote_hint(j, location_name, offices),
        posted_at=posted_at,
        url_canonical=url_canonical,
        raw_json=j,
    )


def _remote_hint(j: dict[str, Any], location: str, offices: str) -> str | None:
    """Best-effort remote-status hint for the classifier downstream."""
    return infer_remote_type(location, offices, str(j.get("title") or "")) or None
