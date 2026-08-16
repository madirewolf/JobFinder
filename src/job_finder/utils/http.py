"""Shared httpx client factory with retries and sane defaults."""

from __future__ import annotations

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .. import logging_config
from ..config import settings

log = logging_config.get_logger(__name__)


def make_client(base_url: str | None = None) -> httpx.AsyncClient:
    """Return an AsyncClient pre-configured with User-Agent, timeout, HTTP/2."""
    headers = {
        "User-Agent": settings.http_user_agent,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-CA,en;q=0.9,fr-CA;q=0.5",
    }
    return httpx.AsyncClient(
        base_url=base_url or "",
        headers=headers,
        timeout=settings.http_timeout_s,
        http2=True,
        follow_redirects=True,
    )


RETRYABLE_STATUSES = frozenset({408, 429, 500, 502, 503, 504})


async def fetch_json(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    attempts: int = 3,
    **kwargs,
) -> dict | list:
    """GET/POST and decode JSON with exponential-backoff retries.

    Retries on connection errors and the retry-able status codes above.
    """

    async for attempt in AsyncRetrying(
        stop=stop_after_attempt(attempts),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        retry=retry_if_exception_type((httpx.TransportError, _Retryable)),
        reraise=True,
    ):
        with attempt:
            resp = await client.request(method, url, **kwargs)
            if resp.status_code in RETRYABLE_STATUSES:
                log.warning(
                    "http.retryable_status",
                    url=url,
                    status=resp.status_code,
                    attempt=attempt.retry_state.attempt_number,
                )
                raise _Retryable(f"status={resp.status_code}")
            resp.raise_for_status()
            return resp.json()

    raise RuntimeError("unreachable")  # pragma: no cover


class _Retryable(Exception):
    """Raised internally so tenacity retries on retry-able HTTP statuses."""
