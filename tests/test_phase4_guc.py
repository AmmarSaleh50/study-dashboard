"""Phase 4 Task 2: app.user_id GUC plumbing.

When `set_current_user_id(uid)` is called for a request, the `app.db.db()`
context manager (and every helper that goes through it) issues
`SET LOCAL app.user_id = '<uid>'` on the connection. This is inert under
the current bypass role but primes the RLS policies (Phase 4 Task 1) for
when prod flips to a non-bypass role.
"""
import pytest


@pytest.mark.asyncio
async def test_app_user_id_guc_set_when_user_context_present(client, db_conn):
    """When a user_id is set in the contextvar, db helpers SET LOCAL it on
    the connection so `current_setting('app.user_id', true)` returns it."""
    from app import db
    from app.auth import set_current_user_id, SENTINEL_USER_ID

    set_current_user_id(SENTINEL_USER_ID)
    try:
        val = await db.fetchval(
            "SELECT current_setting('app.user_id', true)"
        )
        assert val == str(SENTINEL_USER_ID)
    finally:
        set_current_user_id(None)


@pytest.mark.asyncio
async def test_app_user_id_guc_unset_when_no_user_context(client, db_conn):
    """With no contextvar set, db.db() doesn't issue SET LOCAL — Postgres
    returns the empty string for an undefined custom GUC with missing_ok=true."""
    from app import db
    from app.auth import set_current_user_id

    set_current_user_id(None)
    val = await db.fetchval(
        "SELECT current_setting('app.user_id', true)"
    )
    # Postgres returns '' (not NULL) for an undefined GUC when missing_ok=true.
    assert val == "" or val is None
