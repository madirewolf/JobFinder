"""Ollama embeddings wrapper.

Model: nomic-embed-text-v1.5 (768-dim). Free, local, fast enough for our
volume. Embeddings are only cheap if Ollama is actually running — no network
timeout here beyond what the ollama client enforces.

Usage:
    emb = await embed("some text")         # returns list[float] of length 768
    embs = await embed_batch(texts)        # list of lists, preserves order
"""

from __future__ import annotations

import asyncio

from ollama import AsyncClient

from ..config import settings
from ..logging_config import get_logger

log = get_logger(__name__)

EMBED_DIM = 768  # nomic-embed-text-v1.5 output width

_client: AsyncClient | None = None


def _get_client() -> AsyncClient:
    global _client
    if _client is None:
        _client = AsyncClient(host=settings.ollama_host)
    return _client


async def embed(text: str) -> list[float]:
    """Embed one string. Trims to ~8000 chars defensively (nomic limit ≈ 8192 tokens)."""
    if not text or not text.strip():
        raise ValueError("embed() requires non-empty text")
    client = _get_client()
    resp = await client.embeddings(
        model=settings.ollama_embed_model,
        prompt=text[:8000],
    )
    vec = resp["embedding"]
    if len(vec) != EMBED_DIM:
        raise RuntimeError(f"embedding dim mismatch: got {len(vec)}, expected {EMBED_DIM}")
    return list(vec)


async def embed_batch(texts: list[str], concurrency: int = 4) -> list[list[float]]:
    """Embed a batch of strings with bounded concurrency. Preserves input order."""
    sem = asyncio.Semaphore(concurrency)

    async def _one(i: int, t: str) -> tuple[int, list[float]]:
        async with sem:
            return i, await embed(t)

    pairs = await asyncio.gather(*(_one(i, t) for i, t in enumerate(texts)))
    pairs.sort(key=lambda p: p[0])
    return [p[1] for p in pairs]


def format_for_pgvector(vec: list[float]) -> str:
    """Render a python vector as pgvector's text literal format: '[0.1,0.2,...]'.

    Accepts the pgvector text-encoding path even when psycopg's vector adapter
    isn't registered — more portable for raw SQL in migrations and ad-hoc tests.
    """
    return "[" + ",".join(f"{x:.7f}" for x in vec) + "]"
