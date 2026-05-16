"""HTTP endpoint tests for signup / verify-email / forgot-password / reset-password."""
import pytest

from app import db as db_module
from app.services import email as email_svc


def _enable_signups(monkeypatch):
    """Patch env + clear settings cache so SIGNUPS_ENABLED=true takes effect."""
    monkeypatch.setenv("SIGNUPS_ENABLED", "true")
    from app.config import get_settings
    get_settings.cache_clear()


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_signup_endpoint_disabled_returns_403(client, db_conn, monkeypatch):
    """When SIGNUPS_ENABLED is false (default), POST /auth/signup returns 403."""
    monkeypatch.setenv("SIGNUPS_ENABLED", "false")
    from app.config import get_settings
    get_settings.cache_clear()

    resp = await client.post("/api/auth/signup", json={"email": "user@example.com", "password": "password123"})
    assert resp.status_code == 403, resp.text
    assert "signups disabled" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_signup_endpoint_creates_user(client, db_conn, monkeypatch):
    """When SIGNUPS_ENABLED=true, POST /auth/signup returns 200 and creates a user row."""
    _enable_signups(monkeypatch)
    monkeypatch.setenv("EMAIL_BACKEND", "console")
    email_svc.reset_console_outbox()
    from app.config import get_settings
    get_settings.cache_clear()

    resp = await client.post(
        "/api/auth/signup",
        json={"email": "newuser@example.com", "password": "securepass1"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True

    # User row should exist in the DB.
    row = await db_module.fetchrow("SELECT email FROM users WHERE email = %s", "newuser@example.com")
    assert row is not None
    assert row["email"] == "newuser@example.com"


@pytest.mark.asyncio
async def test_signup_endpoint_rate_limited(client, db_conn, monkeypatch):
    """After 5 failed signup attempts (signups disabled), the 6th returns 429."""
    # Keep signups disabled so each attempt triggers a 403 (which is still
    # processed by check_auth_rate first, so the attempt is counted).
    # Actually check_auth_rate runs BEFORE the signup call, and it only counts
    # rows already in auth_attempts. We must seed failures directly.
    monkeypatch.setenv("SIGNUPS_ENABLED", "false")
    from app.config import get_settings
    get_settings.cache_clear()

    # The httpx ASGITransport sets request.client.host = "127.0.0.1", so
    # client_ip() returns "127.0.0.1". Seed 5 failures for that IP.
    for _ in range(5):
        await db_module.execute(
            "INSERT INTO auth_attempts (ip, ok, kind) VALUES (%s, false, 'signup')",
            "127.0.0.1",
        )

    resp = await client.post(
        "/api/auth/signup",
        json={"email": "rate@example.com", "password": "password123"},
    )
    assert resp.status_code == 429, resp.text


@pytest.mark.asyncio
async def test_verify_email_endpoint_bad_token_returns_400(client, db_conn):
    """GET /auth/verify-email with a bogus token returns 400."""
    resp = await client.get("/api/auth/verify-email", params={"token": "not-a-real-token"})
    assert resp.status_code == 400, resp.text
    assert "invalid or expired" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_forgot_password_returns_200_for_unknown_email(client, db_conn):
    """POST /auth/forgot-password always returns 200 even for an unknown email (no enumeration)."""
    resp = await client.post(
        "/api/auth/forgot-password",
        json={"email": "nobody@example.com"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True


@pytest.mark.asyncio
async def test_reset_password_endpoint_bad_token_returns_400(client, db_conn):
    """POST /auth/reset-password with a bogus token returns 400."""
    resp = await client.post(
        "/api/auth/reset-password",
        json={"token": "not-a-real-token", "new_password": "newpassword1"},
    )
    assert resp.status_code == 400, resp.text
    assert "invalid or expired" in resp.json()["detail"]
