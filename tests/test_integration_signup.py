"""End-to-end signup flow integration test.

signup → verify-email → login → forgot-password → reset-password → login with new password.
Drives the full FastAPI app via httpx ASGITransport (no monkeypatched services).
Pulls tokens from the console email backend.
"""
from __future__ import annotations
import re

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

import app.db as db_module
from app.config import get_settings


_TEST_EMAIL = "newuser@test.example"
_TEST_PASSWORD = "supersecret123"
_NEW_PASSWORD = "newsecretpassword456"


@pytest_asyncio.fixture
async def signup_client(db_conn, monkeypatch):
    """https_client equivalent with SIGNUPS_ENABLED=true and EMAIL_BACKEND=console."""
    monkeypatch.setenv("SIGNUPS_ENABLED", "true")
    monkeypatch.setenv("EMAIL_BACKEND", "console")
    monkeypatch.setenv("PUBLIC_URL", "https://test")
    get_settings.cache_clear()
    monkeypatch.setattr(db_module, "_pool", db_conn)

    # Reset email outbox at start
    from app.services import email as email_svc
    email_svc.reset_console_outbox()

    from app.main import create_app
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://test") as ac:
        yield ac
    get_settings.cache_clear()


def _extract_token_from_url(body: str) -> str:
    """Pull token=... out of a URL in the email body."""
    m = re.search(r"token=([A-Za-z0-9_-]+)", body)
    assert m is not None, f"no token found in body: {body!r}"
    return m.group(1)


@pytest.mark.asyncio
async def test_signup_verify_login_forgot_reset_full_flow(signup_client):
    from app.services import email as email_svc

    # 1. Signup
    resp = await signup_client.post("/api/auth/signup", json={
        "email": _TEST_EMAIL, "password": _TEST_PASSWORD,
    })
    assert resp.status_code == 200, resp.text

    # 2. Pull verification token from console outbox
    assert len(email_svc._console_outbox) == 1
    verify_email = email_svc._console_outbox[0]
    assert verify_email["to"] == _TEST_EMAIL
    assert "verify" in verify_email["subject"].lower()
    verify_token = _extract_token_from_url(verify_email["body_text"])

    # 3. Verify
    resp = await signup_client.get(f"/api/auth/verify-email?token={verify_token}")
    assert resp.status_code == 200, resp.text

    # 4. Login with email + password
    resp = await signup_client.post("/api/auth/login", json={
        "email": _TEST_EMAIL, "password": _TEST_PASSWORD,
    })
    assert resp.status_code == 200, resp.text
    assert signup_client.cookies.get("study_session")

    # 5. Forgot password
    email_svc.reset_console_outbox()
    resp = await signup_client.post("/api/auth/forgot-password", json={
        "email": _TEST_EMAIL,
    })
    assert resp.status_code == 200, resp.text

    # 6. Pull reset token
    assert len(email_svc._console_outbox) == 1
    reset_email = email_svc._console_outbox[0]
    assert "reset" in reset_email["subject"].lower()
    reset_token = _extract_token_from_url(reset_email["body_text"])

    # 7. Reset password
    resp = await signup_client.post("/api/auth/reset-password", json={
        "token": reset_token, "new_password": _NEW_PASSWORD,
    })
    assert resp.status_code == 200, resp.text

    # 8. Clear cookies; verify OLD password fails
    signup_client.cookies.clear()
    bad = await signup_client.post("/api/auth/login", json={
        "email": _TEST_EMAIL, "password": _TEST_PASSWORD,
    })
    assert bad.status_code == 401, bad.text

    # 9. NEW password succeeds
    ok = await signup_client.post("/api/auth/login", json={
        "email": _TEST_EMAIL, "password": _NEW_PASSWORD,
    })
    assert ok.status_code == 200, ok.text
    assert signup_client.cookies.get("study_session")


@pytest.mark.asyncio
async def test_signup_disabled_returns_403(db_conn, monkeypatch):
    """Default SIGNUPS_ENABLED=false → 403."""
    monkeypatch.delenv("SIGNUPS_ENABLED", raising=False)
    get_settings.cache_clear()
    monkeypatch.setattr(db_module, "_pool", db_conn)

    from app.main import create_app
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://test") as ac:
        resp = await ac.post("/api/auth/signup", json={
            "email": _TEST_EMAIL, "password": _TEST_PASSWORD,
        })
        assert resp.status_code == 403, resp.text
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_verify_email_with_bad_token_returns_400(signup_client):
    resp = await signup_client.get("/api/auth/verify-email?token=not-a-real-token")
    assert resp.status_code == 400, resp.text


@pytest.mark.asyncio
async def test_forgot_password_unknown_email_still_returns_200(signup_client):
    """No user enumeration: 200 even when email doesn't match a user."""
    resp = await signup_client.post("/api/auth/forgot-password", json={
        "email": "nobody@nowhere.test",
    })
    assert resp.status_code == 200, resp.text
