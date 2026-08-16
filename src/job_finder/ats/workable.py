"""Workable public widget API.

Endpoint:
    GET https://apply.workable.com/api/v1/widget/accounts/{company}

Returns `{ jobs: [...] }`. Each job has a description via a separate detail call:
    GET https://apply.workable.com/api/v3/accounts/{company}/jobs/{shortcode}

Used by: Snowed In, Nuvei, Sangoma, Mila, Botpress.
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

LIST_URL = "https://apply.workable.com/api/v1/widget/accounts/{company}"
DETAIL_URL = "https://apply.workable.com/api/v3/accounts/{company}/jobs/{shortcode}"
DETAIL_CONCURRENCY = 6


async def fetch(token: str) -> list[RawPosting]:
    async with make_client() as client:
        data = await fetch_json(client, "GET", LIST_URL.format(company=token))
        assert isinstance(data, dict)
        jobs_raw = data.get("jobs") or []
        log.info("workable.list.ok", token=token, count=len(jobs_raw))

        sem = asyncio.Semaphore(DETAIL_CONCURRENCY)

        async def hydrate(item: dict[str, Any]) -> RawPosting | None:
            async with sem:
                try:
                    detail = await _get_detail(client, token, item["shortcode"])
                    return _parse(item, detail, token)
                except Exception as e:  # noqa: BLE001
                    log.warning(
                        "workable.detail.fail",
                        token=token,
                        shortcode=item.get("shortcode"),
                        err=str(e),
                    )
                    return None

        results = await asyncio.gather(*(hydrate(it) for it in jobs_raw))
        return [p for p in results if p is not None]


async def _get_detail(client: httpx.AsyncClient, token: str, shortcode: str) -> dict[str, Any]:
    url = DETAIL_URL.format(company=token, shortcode=shortcode)
    data = await fetch_json(client, "GET", url)
    assert isinstance(data, dict)
    return data


def _parse(item: dict[str, Any], detail: dict[str, Any], token: str) -> RawPosting:
    description_html = detail.get("description") or ""
    requirements_html = detail.get("requirements") or ""
    benefits_html = detail.get("benefits") or ""
    description_text = "\n\n".join(
        filter(
            None,
            [
                strip_html(description_html),
                strip_html(requirements_html),
                strip_html(benefits_html),
            ],
        )
    )

    location = item.get("location") or {}
    city = location.get("city")
    region = location.get("region")
    country = location.get("country")
    location_str = ", ".join(part for part in (city, region, country) if part)

    posted_at: datetime | None = None
    if ts := item.get("published_on"):
        try:
            posted_at = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except (TypeError, ValueError):
            posted_at = None

    url_canonical = canonicalize(
        item.get("url") or f"https://apply.workable.com/{token}/j/{item['shortcode']}"
    )

    telecommuting = item.get("telecommuting")
    remote_hint = "remote" if telecommuting else infer_remote_type(location_str, str(item.get("title") or ""))

    return RawPosting(
        source="workable",
        source_rank=1,
        external_id=str(item.get("shortcode") or item.get("id")),
        company_name=token,
        title=str(item.get("title") or "").strip(),
        description_html=description_html,
        description_text=description_text,
        location_raw=location_str or None,
        remote_raw=remote_hint,
        posted_at=posted_at,
        url_canonical=url_canonical,
        raw_json={"list": item, "detail": detail},
    )
