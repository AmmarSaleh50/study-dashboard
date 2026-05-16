"""Tests for app/services/oauth.py.

Security-sensitive: OAuth touches auth-code creation/consumption + bearer-token
storage. Coverage matters more here than other services. The single-use guarantee
on auth codes (consume_auth_code is atomic — DELETE...RETURNING) is what
prevents code-replay attacks; the revoked-flag check on tokens is what makes
revocation actually invalidate a bearer.

Each test uses a fresh client_id (via `_register_client`) so the testcontainer's
session-scoped state doesn't bleed between tests.
"""
from __future__ import annotations

import base64
import hashlib
from datetime import datetime, timedelta, timezone

import pytest

from app.auth import SENTINEL_USER_ID


# ── Helpers ──────────────────────────────────────────────────────────────────

def _pkce_pair(verifier: str = "test-verifier-1234567890abcdefghij") -> tuple[str, str]:
    """Returns (code_verifier, code_challenge_S256) for a known verifier."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


async def _register_client(name: str = "Test Client") -> dict:
    """Register a fresh OAuth client and return the row."""
    from app.services import oauth as svc
    return await svc.create_client(
        client_name=name,
        redirect_uris=["https://example.test/cb"],
        token_endpoint_auth_method="none",
        public=True,
    )


# ── Client registration ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_client_round_trip(client, db_conn):
    """create_client → get_client retrieves the same row."""
    from app.services import oauth as svc
    created = await svc.create_client(
        client_name="My Client",
        redirect_uris=["https://example.test/cb", "https://example.test/cb2"],
        token_endpoint_auth_method="none",
        public=True,
    )
    assert created["client_id"]  # generated id
    assert created["client_name"] == "My Client"
    assert created["redirect_uris"] == [
        "https://example.test/cb",
        "https://example.test/cb2",
    ]
    assert created["token_endpoint_auth_method"] == "none"
    assert created["client_secret"] is None  # public client

    fetched = await svc.get_client(created["client_id"])
    assert fetched is not None
    assert fetched["client_id"] == created["client_id"]
    assert fetched["client_name"] == "My Client"
    assert fetched["redirect_uris"] == created["redirect_uris"]


@pytest.mark.asyncio
async def test_create_confidential_client_has_secret(client, db_conn):
    """Non-public clients get a client_secret."""
    from app.services import oauth as svc
    created = await svc.create_client(
        client_name="Confidential",
        redirect_uris=["https://example.test/cb"],
        token_endpoint_auth_method="client_secret_basic",
        public=False,
    )
    assert created["client_secret"]
    assert created["token_endpoint_auth_method"] == "client_secret_basic"


@pytest.mark.asyncio
async def test_get_client_unknown_returns_none(client, db_conn):
    from app.services import oauth as svc
    assert await svc.get_client("not-a-real-client") is None


# ── Auth codes ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_consume_auth_code_unknown_returns_none(client, db_conn):
    """Unknown auth code → None (not raises)."""
    from app.services import oauth as svc
    verifier, _ = _pkce_pair()
    result = await svc.consume_auth_code(
        "code-that-never-existed",
        client_id="x", redirect_uri="https://example.test/cb",
        code_verifier=verifier,
    )
    assert result is None


@pytest.mark.asyncio
async def test_consume_auth_code_happy_path(client, db_conn):
    """Valid code with correct PKCE verifier returns the row."""
    from app.services import oauth as svc
    cli = await _register_client("Happy Path")
    verifier, challenge = _pkce_pair()
    code = await svc.create_auth_code(
        user_id=SENTINEL_USER_ID,
        client_id=cli["client_id"],
        redirect_uri="https://example.test/cb",
        code_challenge=challenge,
        code_challenge_method="S256",
        scope="mcp",
    )
    row = await svc.consume_auth_code(
        code,
        client_id=cli["client_id"],
        redirect_uri="https://example.test/cb",
        code_verifier=verifier,
    )
    assert row is not None
    assert row["code"] == code
    assert row["client_id"] == cli["client_id"]
    assert row["scope"] == "mcp"


@pytest.mark.asyncio
async def test_consume_auth_code_single_use(client, db_conn):
    """Used auth code → second consume returns None (replay protection)."""
    from app.services import oauth as svc
    cli = await _register_client("Single-Use")
    verifier, challenge = _pkce_pair()
    code = await svc.create_auth_code(
        user_id=SENTINEL_USER_ID,
        client_id=cli["client_id"],
        redirect_uri="https://example.test/cb",
        code_challenge=challenge,
        code_challenge_method="S256",
        scope=None,
    )
    first = await svc.consume_auth_code(
        code, cli["client_id"], "https://example.test/cb", verifier,
    )
    assert first is not None  # first consume succeeds
    second = await svc.consume_auth_code(
        code, cli["client_id"], "https://example.test/cb", verifier,
    )
    assert second is None  # replay rejected


@pytest.mark.asyncio
async def test_consume_auth_code_expired_returns_none(client, db_conn):
    """Expired auth code → None. Backdates expires_at to simulate."""
    from app.services import oauth as svc
    cli = await _register_client("Expired Code")
    verifier, challenge = _pkce_pair()
    code = await svc.create_auth_code(
        user_id=SENTINEL_USER_ID,
        client_id=cli["client_id"],
        redirect_uri="https://example.test/cb",
        code_challenge=challenge,
        code_challenge_method="S256",
        scope=None,
    )
    # Backdate expiry directly via the pool — service has no expiry-mutator.
    async with db_conn.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "UPDATE oauth_auth_codes SET expires_at = %s WHERE code = %s",
            (datetime.now(timezone.utc) - timedelta(seconds=60), code),
        )
    result = await svc.consume_auth_code(
        code, cli["client_id"], "https://example.test/cb", verifier,
    )
    assert result is None


@pytest.mark.asyncio
async def test_consume_auth_code_wrong_client_returns_none(client, db_conn):
    """client_id mismatch → None."""
    from app.services import oauth as svc
    cli = await _register_client("Wrong Client")
    verifier, challenge = _pkce_pair()
    code = await svc.create_auth_code(
        user_id=SENTINEL_USER_ID,
        client_id=cli["client_id"],
        redirect_uri="https://example.test/cb",
        code_challenge=challenge,
        code_challenge_method="S256",
        scope=None,
    )
    result = await svc.consume_auth_code(
        code, "different-client", "https://example.test/cb", verifier,
    )
    assert result is None


@pytest.mark.asyncio
async def test_consume_auth_code_wrong_redirect_returns_none(client, db_conn):
    """redirect_uri mismatch → None."""
    from app.services import oauth as svc
    cli = await _register_client("Wrong Redirect")
    verifier, challenge = _pkce_pair()
    code = await svc.create_auth_code(
        user_id=SENTINEL_USER_ID,
        client_id=cli["client_id"],
        redirect_uri="https://example.test/cb",
        code_challenge=challenge,
        code_challenge_method="S256",
        scope=None,
    )
    result = await svc.consume_auth_code(
        code, cli["client_id"], "https://other.test/cb", verifier,
    )
    assert result is None


@pytest.mark.asyncio
async def test_consume_auth_code_bad_verifier_returns_none(client, db_conn):
    """PKCE verifier doesn't match challenge → None."""
    from app.services import oauth as svc
    cli = await _register_client("Bad Verifier")
    _, challenge = _pkce_pair()
    code = await svc.create_auth_code(
        user_id=SENTINEL_USER_ID,
        client_id=cli["client_id"],
        redirect_uri="https://example.test/cb",
        code_challenge=challenge,
        code_challenge_method="S256",
        scope=None,
    )
    result = await svc.consume_auth_code(
        code,
        cli["client_id"],
        "https://example.test/cb",
        "wrong-verifier-doesnt-match",
    )
    assert result is None


@pytest.mark.asyncio
async def test_consume_auth_code_rejects_plain_method(client, db_conn):
    """OAuth 2.1 mandates S256 — `plain` codes must always be rejected even if
    one slipped into the table (e.g. via a direct POST to /oauth/consent that
    bypasses the /authorize S256 check)."""
    from app.services import oauth as svc
    cli = await _register_client("Plain PKCE")
    code = await svc.create_auth_code(
        user_id=SENTINEL_USER_ID,
        client_id=cli["client_id"],
        redirect_uri="https://example.test/cb",
        code_challenge="literal-challenge",
        code_challenge_method="plain",
        scope=None,
    )
    row = await svc.consume_auth_code(
        code, cli["client_id"], "https://example.test/cb",
        "literal-challenge",
    )
    assert row is None


# ── Access tokens ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_and_verify_access_token(client, db_conn):
    """Issued token validates and carries the client_id + scope."""
    from app.services import oauth as svc
    cli = await _register_client("Token Issue")
    token, expires_in = await svc.create_access_token(SENTINEL_USER_ID, cli["client_id"], "mcp")
    assert token
    assert expires_in > 0
    row = await svc.verify_access_token(token)
    assert row is not None
    assert row["token"] == token
    assert row["client_id"] == cli["client_id"]
    assert row["scope"] == "mcp"
    assert row["revoked"] is False


@pytest.mark.asyncio
async def test_verify_unknown_token_returns_none(client, db_conn):
    from app.services import oauth as svc
    assert await svc.verify_access_token("not-a-real-token") is None


@pytest.mark.asyncio
async def test_token_revocation_invalidates_bearer(client, db_conn):
    """Revoking a token → verify_access_token returns None afterwards."""
    from app.services import oauth as svc
    cli = await _register_client("Revoke")
    token, _ = await svc.create_access_token(SENTINEL_USER_ID, cli["client_id"], "mcp")
    # Pre-revoke: validates fine.
    pre = await svc.verify_access_token(token)
    assert pre is not None
    # Revoke.
    await svc.revoke_token(token)
    # Post-revoke: bearer no longer validates.
    post = await svc.verify_access_token(token)
    assert post is None


@pytest.mark.asyncio
async def test_verify_expired_token_returns_none(client, db_conn):
    """Token past expires_at no longer validates."""
    from app.services import oauth as svc
    cli = await _register_client("Expire Token")
    token, _ = await svc.create_access_token(SENTINEL_USER_ID, cli["client_id"], "mcp")
    # Backdate expiry.
    async with db_conn.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "UPDATE oauth_tokens SET expires_at = %s WHERE token = %s",
            (datetime.now(timezone.utc) - timedelta(seconds=60), token),
        )
    assert await svc.verify_access_token(token) is None


@pytest.mark.asyncio
async def test_bulk_revoke_invalidates_all_tokens(client, db_conn):
    """Bulk UPDATE revoked=true (as run by the Phase-5 migration) causes
    verify_access_token to return None for every previously-valid token."""
    from app.services import oauth as svc
    cli = await _register_client("Bulk Revoke")
    token_a, _ = await svc.create_access_token(SENTINEL_USER_ID, cli["client_id"], "mcp")
    token_b, _ = await svc.create_access_token(SENTINEL_USER_ID, cli["client_id"], "mcp")
    # Both tokens valid before revocation.
    assert await svc.verify_access_token(token_a) is not None
    assert await svc.verify_access_token(token_b) is not None
    # Mirror the migration: UPDATE oauth_tokens SET revoked = true WHERE revoked = false.
    async with db_conn.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "UPDATE oauth_tokens SET revoked = true WHERE revoked = false"
        )
    # Both tokens must now be invalid.
    assert await svc.verify_access_token(token_a) is None
    assert await svc.verify_access_token(token_b) is None
