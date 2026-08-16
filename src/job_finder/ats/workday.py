"""Workday public careers API.

Workday is deliberately left as a scaffold because every tenant has a unique
subdomain, server number, and site path, and small header differences can flip
the endpoint between working and 403. Implement per target as you add them.

Pattern (discovered per tenant by watching browser devtools on the careers page):

    POST https://{tenant}.wd{N}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs
    Content-Type: application/json
    Body:
        {
          "appliedFacets": {},
          "limit": 20,
          "offset": 0,
          "searchText": ""
        }

Example (NVIDIA Americas careers):
    tenant  = "nvidia"
    N       = 5
    site    = "nvidiaexternalcareersite"
    URL     = https://nvidia.wd5.myworkdayjobs.com/wday/cxs/nvidia/nvidiaexternalcareersite/jobs

Store discovered (tenant, wd_server, site) triples in companies.ats_token as
JSON and deserialize here.

Posting detail requires a second call:
    GET https://{tenant}.wd{N}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/job/{id}

Response JSON is deeply nested; the `jobPostingInfo` node has the title and
`jobDescription` HTML.
"""

from __future__ import annotations

from ..logging_config import get_logger
from ..models import RawPosting

log = get_logger(__name__)


async def fetch(token: str) -> list[RawPosting]:
    """Stub. Per-tenant implementation required.

    Expected `token` format: "tenant:wd_server:site_path"
    e.g. "nvidia:5:nvidiaexternalcareersite"
    """
    log.warning(
        "workday.fetch.not_implemented",
        token=token,
        hint="See module docstring for the per-tenant pattern.",
    )
    return []
