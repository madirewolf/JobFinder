"""Tiny metric-events helper. One row per event, tagged JSONB.

Use this everywhere except the ingest inner loop — that one already has a
live `conn` and calls `ingest.repository.record_metric` directly. This
module opens its own connection, so it's fire-and-forget for callers that
don't want to manage one.

Emit on:
  - ingest done/error (already handled in ingest/orchestrator.py)
  - classify.haiku batch done, error
  - rank batch done
  - draft done, error
  - application marked applied
"""

from __future__ import annotations

import json
from typing import Any

from .db import aconn
from .logging_config import get_logger

log = get_logger(__name__)


async def record(metric: str, value: float = 1.0, **tags: Any) -> None:
    """Insert one metric_events row. Swallows DB errors (never the caller's fault)."""
    try:
        async with aconn() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "INSERT INTO metric_events (metric, value, tags) VALUES (%s, %s, %s::jsonb)",
                    (metric, value, json.dumps(tags, default=str)),
                )
            await conn.commit()
    except Exception as e:  # noqa: BLE001
        # Metric telemetry must never crash the job it's measuring.
        log.warning("metric.record.fail", metric=metric, err=str(e))
