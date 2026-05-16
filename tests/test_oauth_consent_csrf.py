"""Regression tests for Bug F: consent CSRF via forged/tampered state.

Each scenario verifies that POST /oauth/consent rejects the request with 400
when the signed oauth_consent_state cookie is absent or mismatched.
"""
from __future__ import annotations

import base64
import hashlib
import secrets

import pytest
import pytest_asyncio
from argon2 import PasswordHasher
from httpx import ASGITransport, AsyncClient

import app.db as db_module
from app.config import get_settings


_TEST_PASSWORD = "test-password-csrf"
_TEST_PASSWORD_HASH = PasswordHasher().hash(_TEST_PASSWORD)
_OPERATOR_EMAIL = "operator@local"


@pytest_asyncio.fixture
async def https_client(db_conn, monkeypatch):
    async with db_conn.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "UPDATE users SET password_hash = %s WHERE email = %s",
            (_TEST_PASSWORD_HASH, _OPERATOR_EMAIL),
        )
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


async def _register_and_login(client: AsyncClient) -> str:
    """Register a client and log in; return the client_id."""
    reg = await client.post(
        "/oauth/register",
        json={
            "client_name": "CSRF Test Client",
            "redirect_uris": ["https://example.test/cb"],
        },
    )
    assert reg.status_code == 201
    client_id = reg.json()["client_id"]

    login = await client.post(
        "/api/auth/login", json={"email": _OPERATOR_EMAIL, "password": _TEST_PASSWORD}
    )
    assert login.status_code == 200
    return client_id


@pytest.mark.asyncio
async def test_consent_without_cookie_rejected(https_client, db_conn):
    """POST /oauth/consent with no oauth_consent_state cookie → 400."""
    client_id = await _register_and_login(https_client)
    _, challenge = _pkce_pair()

    # Deliberately skip /authorize — no cookie is set.
    resp = await https_client.post(
        "/oauth/consent",
        data={
            "client_id": client_id,
            "redirect_uri": "https://example.test/cb",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "scope": "mcp",
            "state": "attacker-state",
        },
    )
    assert resp.status_code == 400, resp.text
    assert "consent state invalid" in resp.text


@pytest.mark.asyncio
async def test_consent_with_wrong_state_rejected(https_client, db_conn):
    """Cookie bound to 'legit-state', but form posts 'evil-state' → 400."""
    client_id = await _register_and_login(https_client)
    _, challenge = _pkce_pair()
    redirect_uri = "https://example.test/cb"
    real_state = "legit-state"

    # GET /authorize with real_state → sets signed cookie.
    auth_resp = await https_client.get(
        "/oauth/authorize",
        params={
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "scope": "mcp",
            "state": real_state,
        },
    )
    assert auth_resp.status_code == 200
    assert https_client.cookies.get("oauth_consent_state")

    # Attacker swaps state in the form body.
    resp = await https_client.post(
        "/oauth/consent",
        data={
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "scope": "mcp",
            "state": "evil-state",
        },
    )
    assert resp.status_code == 400, resp.text
    assert "consent state invalid" in resp.text


@pytest.mark.asyncio
async def test_consent_with_wrong_client_id_rejected(https_client, db_conn):
    """Cookie bound to client_id A, but form posts client_id B → 400."""
    client_id_a = await _register_and_login(https_client)

    # Register a second client.
    reg_b = await https_client.post(
        "/oauth/register",
        json={
            "client_name": "CSRF Test Client B",
            "redirect_uris": ["https://example.test/cb"],
        },
    )
    assert reg_b.status_code == 201
    client_id_b = reg_b.json()["client_id"]

    _, challenge = _pkce_pair()
    redirect_uri = "https://example.test/cb"
    state = "some-state"

    # GET /authorize with client_id_a → cookie bound to client_id_a.
    auth_resp = await https_client.get(
        "/oauth/authorize",
        params={
            "response_type": "code",
            "client_id": client_id_a,
            "redirect_uri": redirect_uri,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "scope": "mcp",
            "state": state,
        },
    )
    assert auth_resp.status_code == 200

    # Attacker swaps client_id in the form.
    resp = await https_client.post(
        "/oauth/consent",
        data={
            "client_id": client_id_b,
            "redirect_uri": redirect_uri,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "scope": "mcp",
            "state": state,
        },
    )
    assert resp.status_code == 400, resp.text
    assert "consent state invalid" in resp.text


@pytest.mark.asyncio
async def test_consent_with_wrong_challenge_rejected(https_client, db_conn):
    """Cookie bound to challenge A, but form posts challenge B → 400."""
    client_id = await _register_and_login(https_client)
    _, challenge_a = _pkce_pair()
    _, challenge_b = _pkce_pair()
    redirect_uri = "https://example.test/cb"
    state = "some-state"

    # GET /authorize with challenge_a → cookie bound to challenge_a.
    auth_resp = await https_client.get(
        "/oauth/authorize",
        params={
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "code_challenge": challenge_a,
            "code_challenge_method": "S256",
            "scope": "mcp",
            "state": state,
        },
    )
    assert auth_resp.status_code == 200

    # Attacker swaps code_challenge in the form.
    resp = await https_client.post(
        "/oauth/consent",
        data={
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "code_challenge": challenge_b,
            "code_challenge_method": "S256",
            "scope": "mcp",
            "state": state,
        },
    )
    assert resp.status_code == 400, resp.text
    assert "consent state invalid" in resp.text
