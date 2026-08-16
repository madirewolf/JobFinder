"""Hacker News "Who is Hiring" monthly thread ingester.

Uses the HN Algolia API (10k req/h, no auth). Each child comment of the thread
is a mini job posting. The format is loose, but most Toronto/Montreal/remote
friendly opportunities follow the convention:

    Company Name | Title | Location | Remote/Onsite | Stack | email

Run once per month. The orchestrator treats the thread-id as the `token`.

API docs: https://hn.algolia.com/api
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from ..logging_config import get_logger
from ..models import RawPosting
from ..utils.canonical import canonicalize
from ..utils.html import strip_html
from ..utils.http import fetch_json, make_client

log = get_logger(__name__)

ITEM_URL = "https://hn.algolia.com/api/v1/items/{item_id}"

# Very loose heuristic; humans write these freeform
COMPANY_TITLE_RE = re.compile(
    r"^\s*([A-Z][\w &.,()'/-]{1,60}?)\s*[\|\-–—:]\s*",
    re.MULTILINE,
)


async def fetch(thread_id: str) -> list[RawPosting]:
    """Fetch one HN thread by ID, return each child comment as a RawPosting."""
    async with make_client() as client:
        data = await fetch_json(client, "GET", ITEM_URL.format(item_id=thread_id))

    assert isinstance(data, dict)
    children = data.get("children") or []
    log.info("hn.fetch.ok", thread_id=thread_id, children=len(children))

    postings: list[RawPosting] = []
    for child in children:
        try:
            p = _parse(child, thread_id)
            if p is not None:
                postings.append(p)
        except Exception as e:  # noqa: BLE001
            log.warning("hn.parse.fail", thread_id=thread_id, id=child.get("id"), err=str(e))
    return postings


def _parse(child: dict[str, Any], thread_id: str) -> RawPosting | None:
    text_html = child.get("text") or ""
    if not text_html:
        return None

    text_plain = strip_html(text_html)
    if len(text_plain) < 30:
        return None  # noise

    company_name, title = _extract_company_and_title(text_plain)

    posted_at: datetime | None = None
    if ts := child.get("created_at_i"):
        posted_at = datetime.fromtimestamp(ts, tz=timezone.utc)

    url = f"https://news.ycombinator.com/item?id={child.get('id')}"

    return RawPosting(
        source="hn",
        source_rank=4,
        external_id=str(child.get("id")),
        company_name=company_name,
        title=title,
        description_html=text_html,
        description_text=text_plain,
        location_raw=None,
        remote_raw=None,
        posted_at=posted_at,
        url_canonical=canonicalize(url),
        raw_json={"thread_id": thread_id, "comment": child},
    )


def _extract_company_and_title(text: str) -> tuple[str, str]:
    """Best-effort split of the first line into (company, title).

    HN posts vary wildly. Fallback: everything before first '|' is the company,
    the next pipe-separated chunk is the title. If no pipes, use first 80 chars.
    """
    first_line = text.strip().splitlines()[0].strip()
    parts = [p.strip() for p in re.split(r"[\|·•]", first_line) if p.strip()]
    if len(parts) >= 2:
        return parts[0][:80], parts[1][:120]
    if m := COMPANY_TITLE_RE.match(first_line):
        company = m.group(1).strip()
        rest = first_line[m.end() :].strip()
        return company[:80], rest[:120] or "Engineering role"
    return "HN Unknown", first_line[:120] or "Engineering role"
