"""Pydantic models shared across the bot.

`RawPosting` is the canonical ingestion DTO. Every ATS client and every non-ATS
ingester normalizes to this shape before the orchestrator inserts into Postgres.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

SourceName = Literal[
    "greenhouse",
    "lever",
    "ashby",
    "smartrecruiters",
    "workable",
    "recruitee",
    "workday",
    "eightfold",
    "hn",
    "remote_ok",
    "wwr",
    "remotive",
    "adzuna",
    "jooble",
    "linkedin",
    "indeed",
    "custom",
]

RemoteType = Literal["remote", "hybrid", "onsite", "unspecified"]


class RawPosting(BaseModel):
    """What every ingester emits.

    Invariants:
      - `url_canonical` is the DB unique key. Strip UTMs, session IDs, sort
        remaining query params before constructing.
      - `description_text` MUST have HTML stripped. See utils.html.strip_html.
      - `raw_json` is the original payload for forensics / re-classification later.
    """

    model_config = ConfigDict(extra="forbid")

    source: SourceName
    source_rank: int = Field(
        default=5,
        ge=1,
        le=9,
        description="1 = ATS direct (most authoritative), 3 = aggregator, 5 = scraped board",
    )
    external_id: str
    company_name: str
    company_domain: str | None = None
    title: str
    description_html: str = ""
    description_text: str
    location_raw: str | None = None
    remote_raw: str | None = None
    posted_at: datetime | None = None
    url_canonical: str
    raw_json: dict[str, Any] = Field(default_factory=dict)


class PostingRow(BaseModel):
    """Thin view of a persisted posting, used by classify + rank + UI."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int
    title: str
    title_normalized: str
    url_canonical: str
    source: str
    source_rank: int
    description_text: str
    first_seen: datetime
    last_seen: datetime
    remote_type: RemoteType
    location: str | None = None
    seniority: str | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    salary_currency: str = "CAD"
    tech_stack: list[str] | None = None
    role_category: str | None = None
    fit_score: float | None = None
    check_risk_score: float | None = None
    final_rank: float | None = None


class CompanySeed(BaseModel):
    """Row loaded from seeds/companies.py into the `companies` table."""

    model_config = ConfigDict(extra="forbid")

    name: str
    domain: str | None = None
    ats_platform: str
    ats_token: str | None = None
    careers_url: HttpUrl | None = None
    bg_check_stringency: Literal["unknown", "lenient", "moderate", "strict", "very_strict"]
    tier: int
    hq_city: str
    hq_province: str
    notes: str | None = None
