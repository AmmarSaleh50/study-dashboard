"""MCP Bearer-token → user_id binding (Phase 5 Task 1).

Verifies that an OAuth access token bound to user A scopes every tool
call invoked with that token to A's data — even when user B also has
overlapping courses, tasks, etc. The contextvar set by
`OAuthTokenVerifier.verify_token` must flow into the tool body that
runs on the same async request.

These tests go over real HTTP (httpx ASGITransport) rather than the
unit-style `mcp_server.fn(...)` harness used elsewhere in tests/mcp/,
because the binding only happens inside the HTTP-served verifier — the
fn-direct path bypasses it entirely.
"""
from __future__ import annotations

from uuid import UUID

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

import app.db as db_module
from app.config import get_settings


_USER_A_ID = "00000000-0000-0000-0000-000000000001"  # operator (already seeded)
_USER_B_ID = "11111111-1111-1111-1111-111111111111"


@pytest_asyncio.fixture
async def https_client(db_conn, monkeypatch):
    """https://test base_url so Secure cookies survive the round-trip."""
    get_settings.cache_clear()
    monkeypatch.setattr(db_module, "_pool", db_conn)

    from app.main import create_app

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://test") as ac:
        yield ac
    get_settings.cache_clear()


async def _seed_two_users_with_courses(db_conn) -> None:
    """Insert user B + one course per user. User A (operator) is pre-seeded."""
    async with db_conn.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "INSERT INTO users (id, email, display_name) VALUES (%s, %s, %s) "
            "ON CONFLICT (id) DO NOTHING",
            (_USER_B_ID, "userb@test.local", "User B"),
        )
        # Course owned by A.
        await cur.execute(
            "INSERT INTO courses (user_id, code, full_name) VALUES (%s, %s, %s)",
            (_USER_A_ID, "ACOURSE", "A's Course"),
        )
        # Course owned by B (same primary key (user_id, code) → two MATHs are fine,
        # but we use distinct codes so the assertion is unambiguous).
        await cur.execute(
            "INSERT INTO courses (user_id, code, full_name) VALUES (%s, %s, %s)",
            (_USER_B_ID, "BCOURSE", "B's Course"),
        )


async def _issue_token_for(
    db_conn, *, client_id: str, user_id: str, token: str
) -> None:
    """Insert an oauth_clients row (if needed) + an oauth_tokens row bound to
    the given user. Bypasses /oauth/register + the authorize-code flow — we
    just want a Bearer token whose verifier resolves to user_id."""
    async with db_conn.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "INSERT INTO oauth_clients (client_id, client_name, redirect_uris) "
            "VALUES (%s, %s, %s) "
            "ON CONFLICT (client_id) DO NOTHING",
            (client_id, "Test Client", ["https://example.test/cb"]),
        )
        await cur.execute(
            "INSERT INTO oauth_tokens "
            "(token, client_id, user_id, scope, expires_at) "
            "VALUES (%s, %s, %s, %s, now() + interval '1 hour')",
            (token, client_id, user_id, "mcp"),
        )


@pytest.mark.asyncio
async def test_bearer_token_scopes_list_courses_to_user_b(https_client, db_conn):
    """A token bound to user B sees only B's courses via tools/call list_courses."""
    await _seed_two_users_with_courses(db_conn)
    token = "test-bearer-token-for-b"
    await _issue_token_for(
        db_conn, client_id="test-client-b", user_id=_USER_B_ID, token=token
    )

    resp = await https_client.post(
        "/mcp/",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        },
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "list_courses", "arguments": {}},
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.text
    # The streamable HTTP response wraps the JSON-RPC payload in either
    # application/json or text/event-stream; in either case the tool's
    # serialized list shows up as JSON in the body text.
    assert "BCOURSE" in body, body[:1000]
    assert "ACOURSE" not in body, body[:1000]


@pytest.mark.asyncio
async def test_bearer_token_scopes_list_courses_to_user_a(https_client, db_conn):
    """The symmetric check: a token bound to user A sees ACOURSE, not BCOURSE."""
    await _seed_two_users_with_courses(db_conn)
    token = "test-bearer-token-for-a"
    await _issue_token_for(
        db_conn, client_id="test-client-a", user_id=_USER_A_ID, token=token
    )

    resp = await https_client.post(
        "/mcp/",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        },
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "list_courses", "arguments": {}},
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.text
    assert "ACOURSE" in body, body[:1000]
    assert "BCOURSE" not in body, body[:1000]


@pytest.mark.asyncio
async def test_verify_token_sets_contextvar(db_conn, monkeypatch):
    """Unit-level: calling the verifier with a known token stamps the
    contextvar with the row's user_id."""
    monkeypatch.setattr(db_module, "_pool", db_conn)

    await _seed_two_users_with_courses(db_conn)
    token = "verifier-unit-token"
    await _issue_token_for(
        db_conn, client_id="verifier-unit-client", user_id=_USER_B_ID, token=token
    )

    # Reset the contextvar to a known state.
    from app.mcp_tools import set_mcp_user_id, _get_mcp_user_id
    set_mcp_user_id(None)

    from app.mcp_http import OAuthTokenVerifier
    verifier = OAuthTokenVerifier(resource="https://test/mcp")
    access = await verifier.verify_token(token)
    assert access is not None
    assert access.client_id == "verifier-unit-client"

    bound = _get_mcp_user_id()
    assert bound == UUID(_USER_B_ID), bound


@pytest.mark.asyncio
async def test_verify_token_expires_at_populated(db_conn, monkeypatch):
    """Bug E: verify_token must populate expires_at from the token row, not None."""
    monkeypatch.setattr(db_module, "_pool", db_conn)

    await _seed_two_users_with_courses(db_conn)
    token = "expires-at-test-token"
    await _issue_token_for(
        db_conn, client_id="expires-at-client", user_id=_USER_B_ID, token=token
    )

    from app.mcp_http import OAuthTokenVerifier
    verifier = OAuthTokenVerifier(resource="https://test/mcp")
    access = await verifier.verify_token(token)

    assert access is not None
    # expires_at must be a future Unix timestamp (token was issued for +1 hour).
    import time
    assert access.expires_at is not None, "expires_at must not be None (Bug E)"
    assert isinstance(access.expires_at, int)
    assert access.expires_at > int(time.time()), "expires_at must be in the future"


@pytest.mark.asyncio
async def test_verify_token_expired_returns_none(db_conn, monkeypatch):
    """An expired token must not be returned — DB WHERE clause filters it out."""
    monkeypatch.setattr(db_module, "_pool", db_conn)

    await _seed_two_users_with_courses(db_conn)
    expired_token = "expired-test-token"
    # Insert a token that is already expired (expires_at in the past).
    async with db_conn.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "INSERT INTO oauth_clients (client_id, client_name, redirect_uris) "
            "VALUES (%s, %s, %s) ON CONFLICT (client_id) DO NOTHING",
            ("expired-client", "Expired Client", ["https://example.test/cb"]),
        )
        await cur.execute(
            "INSERT INTO oauth_tokens "
            "(token, client_id, user_id, scope, expires_at) "
            "VALUES (%s, %s, %s, %s, now() - interval '1 hour')",
            (expired_token, "expired-client", _USER_B_ID, "mcp"),
        )

    from app.mcp_http import OAuthTokenVerifier
    verifier = OAuthTokenVerifier(resource="https://test/mcp")
    access = await verifier.verify_token(expired_token)

    assert access is None, "Expired token must return None"


@pytest.mark.asyncio
async def test_verify_token_unknown_does_not_clobber_contextvar(
    db_conn, monkeypatch
):
    """A bogus bearer must not touch the contextvar — defence against
    accidental cross-request leakage if a verifier ever returned without
    clearing prior state."""
    monkeypatch.setattr(db_module, "_pool", db_conn)

    from app.mcp_tools import set_mcp_user_id, _get_mcp_user_id
    set_mcp_user_id(UUID(_USER_A_ID))

    from app.mcp_http import OAuthTokenVerifier
    verifier = OAuthTokenVerifier(resource="https://test/mcp")
    access = await verifier.verify_token("definitely-not-a-real-token")
    assert access is None
    # Unchanged.
    assert _get_mcp_user_id() == UUID(_USER_A_ID)
