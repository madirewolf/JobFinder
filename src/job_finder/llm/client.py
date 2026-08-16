"""Anthropic Messages API wrapper with cost logging baked in.

Every call goes through `call_messages()`; every call produces a row in
`llm_cost_log`. This is the single choke point for billable LLM traffic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import anthropic

from ..config import settings
from ..db import aconn
from ..logging_config import get_logger
from .pricing import usd_cost

log = get_logger(__name__)

_client: anthropic.AsyncAnthropic | None = None


def _get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        if not settings.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set")
        _client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _client


@dataclass(slots=True)
class LLMResult:
    """Structured result from one Messages call.

    `text` is the concatenated text of all content blocks the model emitted.
    `usage` captures the token counts the API reported, so cost is auditable.
    """

    text: str
    model: str
    operation: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    usd_cost: float
    raw: Any  # the original anthropic Message object (for debug / fallback)


async def call_messages(
    *,
    model: str,
    operation: str,
    system: str | list[dict[str, Any]],
    messages: list[dict[str, Any]],
    max_tokens: int = 2000,
    temperature: float = 0.0,
    log_cost: bool = True,
) -> LLMResult:
    """Call the Anthropic Messages API and log cost.

    `system` may be either a string (uncached) or a list of content blocks —
    use the list form with `cache_control: {"type": "ephemeral"}` to enable
    prompt caching on the system prefix.

    `operation` is a free-form label (e.g. "classify.haiku", "draft.sonnet")
    that lands in llm_cost_log — keep it stable so you can sum by operation.
    """
    client = _get_client()

    resp = await client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system,  # type: ignore[arg-type]
        messages=messages,  # type: ignore[arg-type]
    )

    text = "".join(block.text for block in resp.content if block.type == "text")

    usage = resp.usage
    input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
    output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
    cache_read_tokens = int(getattr(usage, "cache_read_input_tokens", 0) or 0)
    cache_write_tokens = int(getattr(usage, "cache_creation_input_tokens", 0) or 0)

    cost = usd_cost(
        model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_tokens=cache_read_tokens,
        cache_write_tokens=cache_write_tokens,
    )

    if log_cost:
        await _write_cost_log(
            model=model,
            operation=operation,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read_tokens,
            cache_write_tokens=cache_write_tokens,
            usd_cost=cost,
        )

    log.info(
        "llm.call.ok",
        model=model,
        op=operation,
        tok_in=input_tokens,
        tok_out=output_tokens,
        cache_r=cache_read_tokens,
        cache_w=cache_write_tokens,
        usd=round(cost, 6),
    )

    return LLMResult(
        text=text,
        model=model,
        operation=operation,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_tokens=cache_read_tokens,
        cache_write_tokens=cache_write_tokens,
        usd_cost=cost,
        raw=resp,
    )


async def _write_cost_log(
    *,
    model: str,
    operation: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int,
    cache_write_tokens: int,
    usd_cost: float,
) -> None:
    async with aconn() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO llm_cost_log
                    (model, operation, input_tokens, output_tokens,
                     cache_read_tokens, cache_write_tokens, usd_cost)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    model,
                    operation,
                    input_tokens,
                    output_tokens,
                    cache_read_tokens,
                    cache_write_tokens,
                    usd_cost,
                ),
            )
        await conn.commit()
