"""Thin wrapper around psycopg connection pool."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool, ConnectionPool

from .config import settings

_sync_pool: ConnectionPool | None = None
_async_pool: AsyncConnectionPool | None = None


def _sync() -> ConnectionPool:
    global _sync_pool
    if _sync_pool is None:
        _sync_pool = ConnectionPool(
            settings.database_url,
            min_size=1,
            max_size=5,
            kwargs={"row_factory": dict_row},
        )
    return _sync_pool


def _async() -> AsyncConnectionPool:
    global _async_pool
    if _async_pool is None:
        _async_pool = AsyncConnectionPool(
            settings.database_url,
            min_size=1,
            max_size=10,
            kwargs={"row_factory": dict_row},
            open=False,
        )
    return _async_pool


@contextmanager
def conn() -> Iterator[psycopg.Connection]:
    """Synchronous connection; use for CLI and seeds."""
    with _sync().connection() as c:
        yield c


@asynccontextmanager
async def aconn() -> AsyncIterator[psycopg.AsyncConnection]:
    """Async connection; use for ingesters."""
    pool = _async()
    if pool.closed:
        await pool.open()
    async with pool.connection() as c:
        yield c


async def close_pools() -> None:
    global _async_pool, _sync_pool
    if _async_pool is not None and not _async_pool.closed:
        await _async_pool.close()
        _async_pool = None
    if _sync_pool is not None:
        _sync_pool.close()
        _sync_pool = None
