"""Phase 4 RLS enforcement.

The default test connection role bypasses RLS. These tests create a
non-bypass role, switch to it within a transaction, set app.user_id, and
verify policies actually block cross-user access.
"""
from uuid import UUID, uuid4

import pytest


OPERATOR = UUID("00000000-0000-0000-0000-000000000001")

_GRANT_SQL = [
    "GRANT USAGE ON SCHEMA public TO rls_test_user;",
    "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO rls_test_user;",
    "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO rls_test_user;",
]

_CREATE_ROLE_SQL = """
DO $$ BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'rls_test_user') THEN
        CREATE ROLE rls_test_user NOBYPASSRLS LOGIN PASSWORD 'test';
    END IF;
END $$;
"""


async def _ensure_rls_role(cur) -> None:
    """Create rls_test_user (idempotent) and grant table privileges."""
    await cur.execute(_CREATE_ROLE_SQL)
    for sql in _GRANT_SQL:
        await cur.execute(sql)


@pytest.mark.asyncio
async def test_rls_blocks_cross_user_select(client, db_conn):
    """User A's app.user_id should not see User B's courses."""
    second_user = str(uuid4())
    async with db_conn.connection() as conn:
        # Seed rows and create the non-bypass role as superuser.
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO users (id, email, display_name) VALUES (%s, %s, %s)",
                (second_user, f"u-{second_user}@test", "Two"),
            )
            await cur.execute(
                "INSERT INTO courses (user_id, code, full_name) VALUES (%s, %s, %s)",
                (second_user, "USRB", "User B course"),
            )
            await cur.execute(
                "INSERT INTO courses (user_id, code, full_name) VALUES (%s, %s, %s)",
                (str(OPERATOR), "USRA", "User A course"),
            )
            await _ensure_rls_role(cur)

        # Switch role inside a savepoint; SET LOCAL ROLE reverts on RESET ROLE
        # (or end of outer tx). We RESET ROLE explicitly after the block so
        # subsequent superuser work in this test isn't affected.
        async with conn.transaction():
            async with conn.cursor() as cur:
                await cur.execute("SET LOCAL ROLE rls_test_user")
                await cur.execute(
                    "SELECT set_config('app.user_id', %s, true)", (str(OPERATOR),)
                )

                # Should see only OPERATOR's row.
                await cur.execute("SELECT code FROM courses")
                rows = await cur.fetchall()
                codes = {r["code"] for r in rows}
                assert "USRA" in codes, "operator's own course must be visible"
                assert "USRB" not in codes, "other user's course must be hidden by RLS"

        # Restore superuser role so teardown SQL (force_rollback) runs cleanly.
        async with conn.cursor() as cur:
            await cur.execute("RESET ROLE")


@pytest.mark.asyncio
async def test_rls_blocks_cross_user_update(client, db_conn):
    """User A can't UPDATE user B's row even by guessing the code."""
    second_user = str(uuid4())
    async with db_conn.connection() as conn:
        # Seed as superuser.
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO users (id, email, display_name) VALUES (%s, %s, %s)",
                (second_user, f"u2-{second_user}@test", "Two"),
            )
            await cur.execute(
                "INSERT INTO courses (user_id, code, full_name) VALUES (%s, %s, %s)",
                (second_user, "VICX", "User B target"),
            )
            await _ensure_rls_role(cur)

        # Attempt UPDATE as OPERATOR (who does not own VICX).
        async with conn.transaction():
            async with conn.cursor() as cur:
                await cur.execute("SET LOCAL ROLE rls_test_user")
                await cur.execute(
                    "SELECT set_config('app.user_id', %s, true)", (str(OPERATOR),)
                )
                # RLS filters out VICX — the UPDATE matches 0 rows silently.
                await cur.execute(
                    "UPDATE courses SET full_name = 'pwned' WHERE code = 'VICX'"
                )

        # Restore role before reading back.
        async with conn.cursor() as cur:
            await cur.execute("RESET ROLE")

        # Back as superuser: verify the row was NOT updated.
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT full_name FROM courses WHERE user_id = %s AND code = 'VICX'",
                (second_user,),
            )
            row = await cur.fetchone()
            assert row is not None, "seed row must still exist"
            assert row["full_name"] == "User B target", "RLS should have blocked the UPDATE"
