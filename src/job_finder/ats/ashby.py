"""Ashby public job-board API.

Endpoint:
    GET https://api.ashbyhq.com/posting-api/job-board/{company}?includeCompensation=true

No auth. Returns `{ jobs: [...] }` with rich fields including compensation bands
when the employer opts in.
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

BASE_URL = "https://api.ashbyhq.com"


async def fetch(token: str) -> list[RawPosting]:
    url = f"{BASE_URL}/posting-api/job-board/{token}?includeCompensation=true"

    async with make_client() as client:
        log.info("ashby.fetch.start", token=token)
        data = await fetch_json(client, "GET", url)

    assert isinstance(data, dict)
    jobs_raw = data.get("jobs") or []
    log.info("ashby.fetch.ok", token=token, count=len(jobs_raw))

    postings: list[RawPosting] = []
    for j in jobs_raw:
        try:
            postings.append(_parse(j, token))
        except Exception as e:
            log.warning("ashby.parse.fail", token=token, job_id=j.get("id"), err=str(e))
    return postings


def _parse(j: dict[str, Any], token: str) -> RawPosting:
    # Ashby fields: id, title, location, secondaryLocations[], department, team,
    # jobUrl, applyUrl, publishedAt (ISO-8601), descriptionHtml, descriptionPlain,
    # employmentType, isRemote (bool), shouldDisplayCompensationOnJobBoard,
    # compensation
    description_html = j.get("descriptionHtml") or ""
    description_plain = j.get("descriptionPlain") or ""
    description_text = description_plain or strip_html(description_html)

    location = j.get("location")
    secondary = ", ".join(j.get("secondaryLocations") or [])

    posted_at: datetime | None = None
    if ts := j.get("publishedAt"):
        try:
            posted_at = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except (TypeError, ValueError):
            posted_at = None

    url_canonical = canonicalize(j.get("jobUrl") or j.get("applyUrl") or "")

    remote_hint: str | None = None
    if j.get("isRemote") is True:
        remote_hint = "remote"
    else:
        remote_hint = infer_remote_type(location, secondary, str(j.get("title") or ""))

    return RawPosting(
        source="ashby",
        source_rank=1,
        external_id=str(j.get("id")),
        company_name=token,
        title=str(j.get("title") or "").strip(),
        description_html=description_html,
        description_text=description_text,
        location_raw=location or secondary or None,
        remote_raw=remote_hint,
        posted_at=posted_at,
        url_canonical=url_canonical,
        raw_json=j,
    )
