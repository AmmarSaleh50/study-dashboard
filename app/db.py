"""Postgres data access for the FastAPI backend.

Async pool (psycopg3) + helper functions (`fetch`, `fetchrow`, `fetchval`,
`execute`, `db()`). Pool lifecycle is owned by `app/main.py`'s lifespan —
`init_pool()` on startup, `close_pool()` on shutdown.

Services and routers should always go through these helpers; opening
connections by hand defeats the pool. For raw work that needs a transaction
or cursor-level control, `async with db() as conn:` checks one out.
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any

import uuid as _uuid

from psycopg import pq
from psycopg.adapt import Loader
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool


# ── new async pool ────────────────────────────────────────────────────────────

_pool: AsyncConnectionPool | None = None


class _StrUUIDLoaderText(Loader):
    """Load Postgres `uuid` text-protocol columns as Python `str`.

    Pydantic v2 strict mode rejects `uuid.UUID` for fields typed `str`, and
    every entity in OpenStudy has a uuid PK typed `str` in the schemas
    (`Slot.id`, `Lecture.id`, `Task.id`, …). Stringifying at the driver
    level avoids needing a `_row_to_X()` coercer in every service.

    Postgres's text protocol delivers UUIDs as canonical 36-char text
    (`b'a1b2c3d4-e5f6-...'`); we just decode bytes → str.
    """

    format = pq.Format.TEXT

    def load(self, data):
        if isinstance(data, memoryview):
            data = bytes(data)
        return data.decode() if isinstance(data, bytes) else data


class _StrUUIDLoaderBinary(Loader):
    """Load Postgres `uuid` binary-protocol columns as Python `str`.

    Twin of `_StrUUIDLoaderText`. Binary protocol delivers UUIDs as 16 raw
    bytes — we wrap with `uuid.UUID(bytes=…)` to get the canonical text,
    then `str()` to match the text-loader's output. Without this, psycopg
    falls back to its built-in `UUIDBinaryLoader` which returns
    `uuid.UUID`, and Pydantic strict-mode rejects that for `str` fields.
    """

    format = pq.Format.BINARY

    def load(self, data):
        if isinstance(data, memoryview):
            data = bytes(data)
        return str(_uuid.UUID(bytes=data))


async def _configure_connection(conn) -> None:
    """Per-connection adapter setup. Runs once on every freshly-opened
    connection in the pool (psycopg's `configure=` callback). We register
    BOTH text and binary loaders so the loader runs regardless of the
    cursor's protocol — defensive against psycopg's choice changing under
    us between cursor instantiations or driver versions."""
    conn.adapters.register_loader("uuid", _StrUUIDLoaderText)
    conn.adapters.register_loader("uuid", _StrUUIDLoaderBinary)


def _build_dsn() -> str:
    """Build the Postgres DSN from POSTGRES_* env vars (same shape as
    scripts/run_migrations.py uses)."""
    user = os.environ["POSTGRES_USER"]
    pw = os.environ["POSTGRES_PASSWORD"]
    db_ = os.environ["POSTGRES_DB"]
    host = os.environ.get("PGHOST", "postgres")
    port = os.environ.get("PGPORT", "5432")
    return f"postgresql://{user}:{pw}@{host}:{port}/{db_}"


async def init_pool(dsn: str | None = None) -> None:
    """Create the global async pool. Idempotent — safe to call once during
    app startup. The lifespan in app/main.py is the canonical caller."""
    global _pool
    if _pool is not None:
        return
    _pool = AsyncConnectionPool(
        dsn or _build_dsn(),
        min_size=2,
        max_size=10,
        open=False,
        # dict_row factory — every cursor returns dict-shaped rows so
        # services use `row["column"]` access (same shape Pydantic's
        # `model_validate(row)` consumes).
        kwargs={"row_factory": dict_row},
        # Per-connection adapter setup so UUID columns load as `str`
        # rather than `uuid.UUID` (Pydantic-friendly).
        configure=_configure_connection,
    )
    await _pool.open()


async def close_pool() -> None:
    """Close the global pool. Called during app shutdown."""
    global _pool
    if _pool is None:
        return
    await _pool.close()
    _pool = None


def pool() -> AsyncConnectionPool:
    if _pool is None:
        raise RuntimeError("DB pool not initialised — call init_pool() first.")
    return _pool


@asynccontextmanager
async def db():
    """`async with db() as conn:` — checks out a connection from the pool."""
    async with pool().connection() as conn:
        yield conn


# ── helper API ────────────────────────────────────────────────────────────────

async def fetch(sql: str, *args: Any) -> list[dict[str, Any]]:
    """SELECT returning multiple rows. Returns list of dicts."""
    async with db() as conn, conn.cursor() as cur:
        await cur.execute(sql, args or None)
        return await cur.fetchall()


async def fetchrow(sql: str, *args: Any) -> dict[str, Any] | None:
    """SELECT returning one row (or None). Returns dict or None."""
    async with db() as conn, conn.cursor() as cur:
        await cur.execute(sql, args or None)
        return await cur.fetchone()


async def fetchval(sql: str, *args: Any) -> Any:
    """SELECT returning one scalar (or None). Returns the first column of the first row."""
    async with db() as conn, conn.cursor() as cur:
        await cur.execute(sql, args or None)
        row = await cur.fetchone()
        if row is None:
            return None
        # row is a dict (dict_row factory) — return its first value
        return next(iter(row.values()))


async def execute(sql: str, *args: Any) -> int:
    """INSERT/UPDATE/DELETE. Returns affected row count."""
    async with db() as conn, conn.cursor() as cur:
        await cur.execute(sql, args or None)
        return cur.rowcount
