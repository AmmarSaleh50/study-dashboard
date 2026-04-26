"""Idempotent SQL migration runner.

Reads `migrations/*.sql` (sorted by filename), applies each file not yet
recorded in the `_migrations` tracking table, and records the file's sha256
so re-runs are no-ops and edits to already-applied files surface as drift
errors instead of silent skips. Each file runs inside a single transaction
so a failure aborts cleanly with no partial state.

Invoked automatically by `./deploy.sh` before the openstudy container starts,
and runnable ad-hoc via:
    docker compose run --rm --no-deps openstudy \\
        uv run --no-sync python scripts/run_migrations.py

Connection string is built from the standard Postgres env vars
(`POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`) and assumes the
Postgres container is reachable at hostname `postgres` (the internal
docker service name). Override with `PGHOST` / `PGPORT` if running outside
the default compose network.
"""
from __future__ import annotations

import hashlib
import os
import sys
import time
from pathlib import Path

import psycopg


MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


def conn_str() -> str:
    user = os.environ["POSTGRES_USER"]
    pw = os.environ["POSTGRES_PASSWORD"]
    db = os.environ["POSTGRES_DB"]
    host = os.environ.get("PGHOST", "postgres")
    port = os.environ.get("PGPORT", "5432")
    return f"postgresql://{user}:{pw}@{host}:{port}/{db}"


def wait_for_postgres(dsn: str, timeout_s: int = 60) -> None:
    """Block until the postgres server accepts connections, or timeout."""
    deadline = time.monotonic() + timeout_s
    last_err: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with psycopg.connect(dsn, connect_timeout=3) as c:
                c.execute("SELECT 1")
                return
        except Exception as e:
            last_err = e
            time.sleep(1)
    raise RuntimeError(f"postgres not ready after {timeout_s}s: {last_err}")


def ensure_migrations_table(conn: psycopg.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS _migrations (
            filename   TEXT PRIMARY KEY,
            checksum   TEXT NOT NULL,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    conn.commit()


def list_pending(conn: psycopg.Connection) -> list[Path]:
    if not MIGRATIONS_DIR.exists():
        raise RuntimeError(f"migrations dir missing: {MIGRATIONS_DIR}")
    on_disk = sorted(MIGRATIONS_DIR.glob("*.sql"))
    cur = conn.execute("SELECT filename, checksum FROM _migrations")
    applied = {row[0]: row[1] for row in cur.fetchall()}
    pending: list[Path] = []
    for f in on_disk:
        sha = hashlib.sha256(f.read_bytes()).hexdigest()
        if f.name not in applied:
            pending.append(f)
        elif applied[f.name] != sha:
            raise RuntimeError(
                f"migration drift: {f.name} on disk has different checksum "
                f"than the one recorded in _migrations. Migrations are immutable "
                f"once applied — create a new file to amend."
            )
    return pending


_OUTER_TX = ("begin", "begin transaction", "commit", "end", "rollback")


def _strip_outer_transaction(sql: str) -> str:
    """Strip leading `BEGIN;` and trailing `COMMIT;`/`END;` from a migration file.

    Migration files often wrap their statements in `begin;...commit;` so they're
    safe when run manually via psql. Our runner already wraps each file in
    `with conn.transaction()`, and a nested SQL-level BEGIN errors out as a
    savepoint mismatch. So strip ONLY the outermost top-level transaction
    control statements.

    Critically, this must NOT strip `begin`/`end` inside `$$ ... $$` plpgsql
    function bodies (where they're block markers, not transaction control).
    Approach: walk lines, only consider stripping when not inside a $$ region,
    and only at file start (before any other non-comment statement) or file end
    (after all statements). Conservative: leave anything ambiguous alone.
    """
    lines = sql.splitlines()

    # Track $$-quoted regions so we don't touch plpgsql block syntax inside them.
    in_dollar = False
    dollar_tag = ""

    # First pass: find indices of leading BEGIN and trailing COMMIT (only when
    # at outermost level, only at file boundaries).
    leading_idx = -1
    trailing_idx = -1
    seen_real_stmt = False
    for i, raw in enumerate(lines):
        # Track $$ enter/exit (very simple matcher — assumes one tag per line max)
        if "$$" in raw:
            # toggle each $$ found
            count = raw.count("$$")
            for _ in range(count):
                in_dollar = not in_dollar
        if in_dollar:
            seen_real_stmt = True
            continue
        stripped = raw.strip()
        if not stripped or stripped.startswith("--"):
            continue
        normalized = stripped.rstrip(";").lower()
        if normalized in _OUTER_TX:
            if not seen_real_stmt and leading_idx == -1:
                leading_idx = i
            else:
                trailing_idx = i  # remember the last seen one
        else:
            seen_real_stmt = True

    out: list[str] = []
    for i, raw in enumerate(lines):
        if i == leading_idx or i == trailing_idx:
            continue
        out.append(raw)
    return "\n".join(out)


def apply(conn: psycopg.Connection, sql_file: Path) -> None:
    raw_sql = sql_file.read_text(encoding="utf-8")
    sha = hashlib.sha256(raw_sql.encode("utf-8")).hexdigest()
    sql = _strip_outer_transaction(raw_sql)
    print(f"  applying {sql_file.name} ({len(raw_sql)} bytes, sha {sha[:12]})...")
    with conn.transaction():
        conn.execute(sql)
        conn.execute(
            "INSERT INTO _migrations (filename, checksum) VALUES (%s, %s)",
            (sql_file.name, sha),
        )


def main() -> int:
    dsn = conn_str()
    print(f"migrations: connecting to {dsn.split('@')[-1]}...")
    wait_for_postgres(dsn)
    with psycopg.connect(dsn, autocommit=False) as conn:
        ensure_migrations_table(conn)
        pending = list_pending(conn)
        if not pending:
            print("migrations: nothing to apply (database is up to date)")
            return 0
        print(f"migrations: {len(pending)} pending file(s)")
        for f in pending:
            try:
                apply(conn, f)
            except Exception as e:
                print(f"  FAILED on {f.name}: {e}", file=sys.stderr)
                conn.rollback()
                return 1
        print(f"migrations: applied {len(pending)} file(s) successfully")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
