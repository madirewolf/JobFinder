"""SmartRecruiters public postings API.

Endpoint:
    GET https://api.smartrecruiters.com/v1/companies/{companyId}/postings
        ?limit=100&offset=0&city=Toronto

No auth for GET. OpenAPI-documented. We fetch postings, then hydrate each with
GET /v1/companies/{companyId}/postings/{postingId} for full description HTML.

Used by: Ubisoft, Klick, Geotab, Rodeo FX, Don't Nod, Compulsion Games, Gameloft.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

import httpx

from ..logging_config import get_logger
from ..models import RawPosting
from ..utils.canonical import canonicalize
from ..utils.html import strip_html
from ..utils.http import fetch_json, make_client
from .base import infer_remote_type

log = get_logger(__name__)

BASE_URL = "https://api.smartrecruiters.com"
PAGE_SIZE = 100
DETAIL_CONCURRENCY = 6


async def fetch(token: str) -> list[RawPosting]:
    """Fetch all postings for SmartRecruiters company `token`.

    Token is the company's URL slug (e.g. "Ubisoft", "Klick").
    """
    async with make_client() as client:
        listings = await _list_all(client, token)
        log.info("smartrecruiters.list.ok", token=token, count=len(listings))

        # Hydrate details in parallel, bounded concurrency
        sem = asyncio.Semaphore(DETAIL_CONCURRENCY)

        async def hydrate(item: dict[str, Any]) -> RawPosting | None:
            async with sem:
                try:
                    detail = await _get_detail(client, token, item["id"])
                    return _parse(item, detail, token)
                except Exception as e:  # noqa: BLE001
                    log.warning(
                        "smartrecruiters.detail.fail",
                        token=token,
                        id=item.get("id"),
                        err=str(e),
                    )
                    return None

        results = await asyncio.gather(*(hydrate(it) for it in listings))
        return [p for p in results if p is not None]


async def _list_all(client: httpx.AsyncClient, token: str) -> list[dict[str, Any]]:
    """Paginate all live postings for a company."""
    out: list[dict[str, Any]] = []
    offset = 0
    while True:
        url = f"{BASE_URL}/v1/companies/{token}/postings?limit={PAGE_SIZE}&offset={offset}"
        data = await fetch_json(client, "GET", url)
        assert isinstance(data, dict)
        items = data.get("content") or []
        out.extend(items)
        total = data.get("totalFound") or 0
        offset += len(items)
        if not items or offset >= total:
            break
    return out


async def _get_detail(client: httpx.AsyncClient, token: str, posting_id: str) -> dict[str, Any]:
    url = f"{BASE_URL}/v1/companies/{token}/postings/{posting_id}"
    data = await fetch_json(client, "GET", url)
    assert isinstance(data, dict)
    return data


def _parse(item: dict[str, Any], detail: dict[str, Any], token: str) -> RawPosting:
    # Merge list-item fields with detail fields. Detail has jobAd.sections.*
    # with HTML for jobDescription, qualifications, additionalInformation.
    job_ad = detail.get("jobAd") or {}
    sections = job_ad.get("sections") or {}

    def _section(key: str) -> str:
        sec = sections.get(key) or {}
        return strip_html(sec.get("text") or "")

    description_parts = [
        _section("jobDescription"),
        _section("qualifications"),
        _section("additionalInformation"),
    ]
    description_text = "\n\n".join(p for p in description_parts if p)
    description_html = (sections.get("jobDescription") or {}).get("text") or ""

    location = item.get("location") or {}
    city = location.get("city")
    region = location.get("region")
    country = location.get("country")
    location_str = ", ".join(part for part in (city, region, country) if part)

    posted_at: datetime | None = None
    if ts := item.get("releasedDate"):
        try:
            posted_at = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except (TypeError, ValueError):
            posted_at = None

    url_canonical = canonicalize(
        detail.get("postingUrl") or item.get("ref") or f"https://jobs.smartrecruiters.com/{token}/{item['id']}"
    )

    return RawPosting(
        source="smartrecruiters",
        source_rank=1,
        external_id=str(item.get("id")),
        company_name=token,
        title=str(item.get("name") or detail.get("name") or "").strip(),
        description_html=description_html,
        description_text=description_text,
        location_raw=location_str or None,
        remote_raw=infer_remote_type(location_str, str(item.get("name") or "")),
        posted_at=posted_at,
        url_canonical=url_canonical,
        raw_json={"list": item, "detail": detail},
    )
