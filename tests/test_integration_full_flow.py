"""End-to-end multi-step integration tests over real HTTP.

Each test drives the FastAPI app via an ASGI httpx client (no
`dependency_overrides`), so cookies, OAuth Bearer tokens, and the
rate-limit table are exercised the same way a real client would.

base_url is `https://test` because `issue_session` sets the cookie with
`secure=True` — httpx won't send Secure cookies back over an http origin.
"""
from __future__ import annotations

import base64
import hashlib
import secrets

import pyotp
import pytest
import pytest_asyncio
from argon2 import PasswordHasher
from httpx import ASGITransport, AsyncClient

import app.db as db_module
from app.config import get_settings


_TEST_PASSWORD = "test-password-1234"
_TEST_PASSWORD_HASH = PasswordHasher().hash(_TEST_PASSWORD)


@pytest_asyncio.fixture
async def https_client(db_conn, monkeypatch):
    """Like the conftest `client` fixture but with `https://test` base_url
    so Secure cookies survive the round-trip, plus a known
    APP_PASSWORD_HASH so /api/auth/login can succeed."""
    monkeypatch.setenv("APP_PASSWORD_HASH", _TEST_PASSWORD_HASH)
    get_settings.cache_clear()
    monkeypatch.setattr(db_module, "_pool", db_conn)

    from app.main import create_app

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://test") as ac:
        yield ac
    get_settings.cache_clear()


def _pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


@pytest.mark.asyncio
async def test_oauth_full_lifecycle(https_client, db_conn):
    redirect_uri = "https://example.test/cb"

    # 1. Dynamic Client Registration.
    reg = await https_client.post(
        "/oauth/register",
        json={"client_name": "Full Flow", "redirect_uris": [redirect_uri]},
    )
    assert reg.status_code == 201, reg.text
    client_id = reg.json()["client_id"]

    # 2. Login with the test password (no TOTP yet).
    login = await https_client.post(
        "/api/auth/login", json={"password": _TEST_PASSWORD}
    )
    assert login.status_code == 200, login.text
    assert https_client.cookies.get("study_session")

    # 3. Consent → 302 to redirect_uri with ?code=…
    verifier, challenge = _pkce_pair()
    state = "state-xyz"
    consent = await https_client.post(
        "/oauth/consent",
        data={
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "scope": "mcp",
            "state": state,
        },
    )
    assert consent.status_code == 302, consent.text
    location = consent.headers["location"]
    assert location.startswith(redirect_uri + "?"), location
    # Pull the `code` out of the query.
    from urllib.parse import urlparse, parse_qs
    qs = parse_qs(urlparse(location).query)
    assert qs.get("state") == [state]
    code = qs["code"][0]

    # 4. Exchange code for an access token.
    tok = await https_client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": client_id,
            "code_verifier": verifier,
        },
    )
    assert tok.status_code == 200, tok.text
    access_token = tok.json()["access_token"]

    # 5. POST /mcp/ tools/list with Bearer auth → must succeed.
    mcp_resp = await https_client.post(
        "/mcp/",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        },
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
    )
    assert mcp_resp.status_code == 200, mcp_resp.text
    body = mcp_resp.text
    # The response is either application/json or text/event-stream; both
    # carry the JSON-RPC payload as text. We just check that some tools
    # show up — `list_courses` is registered unconditionally.
    assert "list_courses" in body, body[:500]

    # 6. Revoke via the RFC 7009 endpoint.
    revoke = await https_client.post(
        "/oauth/revoke", data={"token": access_token, "client_id": client_id}
    )
    assert revoke.status_code == 200, revoke.text

    # 7. Repeat /mcp/ — Bearer token now invalid → 401.
    mcp_resp_2 = await https_client.post(
        "/mcp/",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        },
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    )
    assert mcp_resp_2.status_code == 401, mcp_resp_2.text


@pytest.mark.asyncio
async def test_login_rate_limit_then_success(https_client, db_conn):
    # 5 failed attempts: each 401 with "invalid password".
    for _ in range(5):
        bad = await https_client.post(
            "/api/auth/login", json={"password": "wrong"}
        )
        assert bad.status_code == 401, bad.text

    # 6th attempt: bucket is full → 429 BEFORE reaching verify_password.
    capped = await https_client.post(
        "/api/auth/login", json={"password": "wrong"}
    )
    assert capped.status_code == 429, capped.text

    # Even a correct password is rejected once rate-limited (the limit is
    # checked BEFORE verify_password).
    still_capped = await https_client.post(
        "/api/auth/login", json={"password": _TEST_PASSWORD}
    )
    assert still_capped.status_code == 429

    # Clear the limiter by deleting attempts on the same conn the limiter
    # reads through (the test's _TxnPool — see conftest).
    async with db_conn.connection() as conn, conn.cursor() as cur:
        await cur.execute("DELETE FROM auth_attempts")

    # Correct password now succeeds.
    ok = await https_client.post(
        "/api/auth/login", json={"password": _TEST_PASSWORD}
    )
    assert ok.status_code == 200, ok.text
    assert https_client.cookies.get("study_session")

    # And an authenticated route works with the cookie.
    dash = await https_client.get("/api/dashboard")
    assert dash.status_code == 200, dash.text


@pytest.mark.asyncio
async def test_totp_enroll_and_login(https_client, db_conn):
    # 1. Login with password only (TOTP not yet enabled).
    login = await https_client.post(
        "/api/auth/login", json={"password": _TEST_PASSWORD}
    )
    assert login.status_code == 200, login.text

    # 2. TOTP setup → fresh secret.
    setup = await https_client.post("/api/auth/totp/setup")
    assert setup.status_code == 200, setup.text
    secret = setup.json()["secret"]
    assert secret

    # 3. Enable with a valid code.
    enable = await https_client.post(
        "/api/auth/totp/enable", json={"code": pyotp.TOTP(secret).now()}
    )
    assert enable.status_code == 200, enable.text
    assert enable.json()["totp_enabled"] is True

    # Drop the cookie so subsequent /login attempts are unauthenticated.
    https_client.cookies.clear()

    # 4. Password without code → 401 totp_required.
    pw_only = await https_client.post(
        "/api/auth/login", json={"password": _TEST_PASSWORD}
    )
    assert pw_only.status_code == 401, pw_only.text
    assert pw_only.json()["detail"] == "totp_required"

    # 5. Password + wrong code → 401 invalid totp.
    bad_code = await https_client.post(
        "/api/auth/login",
        json={"password": _TEST_PASSWORD, "totp_code": "000000"},
    )
    assert bad_code.status_code == 401, bad_code.text
    assert bad_code.json()["detail"] == "invalid totp code"

    # 6. Password + correct code → 200, cookie set.
    good = await https_client.post(
        "/api/auth/login",
        json={
            "password": _TEST_PASSWORD,
            "totp_code": pyotp.TOTP(secret).now(),
        },
    )
    assert good.status_code == 200, good.text
    assert https_client.cookies.get("study_session")
