"""Postgres data access for the FastAPI backend.

Two coexisting interfaces during the PostgREST → direct-Postgres migration:

- **NEW (preferred):** async pool + helper functions (`fetch`, `fetchrow`,
  `fetchval`, `execute`, `db()`). Backed by psycopg3's AsyncConnectionPool.
  All new code uses this; migrated services use this.

- **LEGACY (`client()`):** synchronous PostgREST shim. Still here so
  un-migrated services keep working during the transition. Removed at
  the end of Batch C1 (Phase 3).

Pool lifecycle is owned by `app/main.py`'s lifespan — `init_pool()` on
startup, `close_pool()` on shutdown.
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from functools import lru_cache
from typing import Any

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from .config import get_settings


# ── new async pool ────────────────────────────────────────────────────────────

_pool: AsyncConnectionPool | None = None


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
        # services can keep using `row["column"]` access. Same shape
        # PostgREST returned in `resp.data`.
        kwargs={"row_factory": dict_row},
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


# ── LEGACY postgrest client (removed at end of Batch C1 Phase 3) ──────────────

@lru_cache
def client() -> "_Client":
    from postgrest import SyncPostgrestClient
    s = get_settings()
    if not s.postgrest_url:
        raise RuntimeError("POSTGREST_URL must be set.")
    rest_url = s.postgrest_url.rstrip("/")
    headers: dict[str, str] = {}
    if s.postgrest_auth:
        if not s.postgrest_api_key:
            raise RuntimeError(
                "POSTGREST_API_KEY required when POSTGREST_AUTH=true."
            )
        headers = {
            "apikey": s.postgrest_api_key,
            "Authorization": f"Bearer {s.postgrest_api_key}",
        }
    pg = SyncPostgrestClient(rest_url, headers=headers)
    return _Client(pg)


class _Client:
    """Shim exposing the same `.table(name)` / `.rpc(name, params)` API the
    existing services use."""

    def __init__(self, pg):
        self._pg = pg

    def table(self, name: str):
        return self._pg.from_(name)
