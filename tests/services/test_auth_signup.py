"""Tests for app/services/auth_signup.py — signup/verify/forgot/reset flows."""
import re
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from app.services import email as email_svc


# ── Helpers ───────────────────────────────────────────────────────────────────


def _enable_signups(monkeypatch):
    """Patch env + clear settings cache so SIGNUPS_ENABLED=true takes effect."""
    monkeypatch.setenv("SIGNUPS_ENABLED", "true")
    from app.config import get_settings
    get_settings.cache_clear()


def _extract_url_from_text(body_text: str) -> str:
    """Pull the first http(s) URL out of an email body_text."""
    match = re.search(r"https?://\S+", body_text)
    assert match, f"No URL found in email body: {body_text!r}"
    return match.group(0)


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_signup_creates_user_and_sends_email(client, db_conn, monkeypatch):
    """Happy path: signup with SIGNUPS_ENABLED=true creates a users row and
    sends a verification email to the console outbox."""
    _enable_signups(monkeypatch)
    monkeypatch.setenv("EMAIL_BACKEND", "console")
    email_svc.reset_console_outbox()

    from app.services import auth_signup as svc
    from app.config import get_settings
    get_settings.cache_clear()

    user_id = await svc.signup("Test.User@Example.COM", "s3cr3t-pass!")

    # Returns a valid UUID.
    assert isinstance(user_id, UUID)

    # A users row was created with the normalised email.
    from app import db
    row = await db.fetchrow("SELECT email, email_verified_at FROM users WHERE id = %s", str(user_id))
    assert row is not None
    assert row["email"] == "test.user@example.com"
    assert row["email_verified_at"] is None

    # Verification email was sent.
    assert len(email_svc._console_outbox) == 1
    sent = email_svc._console_outbox[0]
    assert sent["to"] == "test.user@example.com"
    assert "verify" in sent["subject"].lower()
    assert "verify-email?token=" in sent["body_text"]


@pytest.mark.asyncio
async def test_signup_disabled_raises(client, db_conn, monkeypatch):
    """When SIGNUPS_ENABLED=false (default), signup raises ValueError."""
    monkeypatch.setenv("SIGNUPS_ENABLED", "false")
    from app.config import get_settings
    get_settings.cache_clear()

    from app.services import auth_signup as svc
    with pytest.raises(ValueError, match="signups disabled"):
        await svc.signup("anyone@example.com", "password123")


@pytest.mark.asyncio
async def test_signup_duplicate_email_is_silent_idempotent(client, db_conn, monkeypatch):
    """Signing up with an already-registered email returns the existing user's id
    silently — no second email is sent."""
    _enable_signups(monkeypatch)
    monkeypatch.setenv("EMAIL_BACKEND", "console")
    email_svc.reset_console_outbox()

    from app.services import auth_signup as svc
    from app.config import get_settings
    get_settings.cache_clear()

    first_id = await svc.signup("dup@example.com", "pass-one")
    outbox_after_first = len(email_svc._console_outbox)

    second_id = await svc.signup("dup@example.com", "pass-two")

    # Same user id returned.
    assert first_id == second_id
    # No additional email sent.
    assert len(email_svc._console_outbox) == outbox_after_first


@pytest.mark.asyncio
async def test_verify_email_marks_verified(client, db_conn, monkeypatch):
    """After signup, pulling the token from the outbox and calling verify_email
    sets email_verified_at on the users row."""
    _enable_signups(monkeypatch)
    monkeypatch.setenv("EMAIL_BACKEND", "console")
    email_svc.reset_console_outbox()

    from app.services import auth_signup as svc
    from app.config import get_settings
    from app import db
    get_settings.cache_clear()

    user_id = await svc.signup("verify-me@example.com", "pass123!")

    # Extract token from the URL in the email body.
    body_text = email_svc._console_outbox[0]["body_text"]
    url = _extract_url_from_text(body_text)
    token = url.split("token=")[-1]

    result = await svc.verify_email(token)
    assert result is True

    row = await db.fetchrow(
        "SELECT email_verified_at FROM users WHERE id = %s", str(user_id)
    )
    assert row is not None
    assert row["email_verified_at"] is not None


@pytest.mark.asyncio
async def test_verify_email_expired_returns_false(client, db_conn, monkeypatch):
    """A token whose expires_at is in the past is rejected and returns False."""
    _enable_signups(monkeypatch)
    monkeypatch.setenv("EMAIL_BACKEND", "console")
    email_svc.reset_console_outbox()

    from app.services import auth_signup as svc
    from app.config import get_settings
    get_settings.cache_clear()

    await svc.signup("expire-me@example.com", "pass123!")

    body_text = email_svc._console_outbox[0]["body_text"]
    url = _extract_url_from_text(body_text)
    token = url.split("token=")[-1]

    # Backdate the token's expiry so it looks expired.
    async with db_conn.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "UPDATE email_verifications SET expires_at = %s WHERE token = %s",
            (datetime.now(timezone.utc) - timedelta(hours=1), token),
        )

    result = await svc.verify_email(token)
    assert result is False


@pytest.mark.asyncio
async def test_request_password_reset_silent_on_unknown_email(client, db_conn, monkeypatch):
    """request_password_reset with a non-existent email returns silently and
    sends no email."""
    monkeypatch.setenv("EMAIL_BACKEND", "console")
    email_svc.reset_console_outbox()
    from app.config import get_settings
    get_settings.cache_clear()

    from app.services import auth_signup as svc
    await svc.request_password_reset("nobody@example.com")

    assert len(email_svc._console_outbox) == 0


@pytest.mark.asyncio
async def test_complete_password_reset_updates_hash(client, db_conn, monkeypatch):
    """Full reset flow: signup → request_password_reset → pull token from outbox
    → complete_password_reset → verify old hash is replaced."""
    _enable_signups(monkeypatch)
    monkeypatch.setenv("EMAIL_BACKEND", "console")
    email_svc.reset_console_outbox()

    from app.services import auth_signup as svc
    from app.config import get_settings
    from app import db
    from argon2 import PasswordHasher

    get_settings.cache_clear()
    ph = PasswordHasher()

    user_id = await svc.signup("reset-me@example.com", "old-pass!")

    # Capture the old password hash.
    row_before = await db.fetchrow(
        "SELECT password_hash FROM users WHERE id = %s", str(user_id)
    )
    old_hash = row_before["password_hash"]

    # Clear verification outbox, then request a reset.
    email_svc.reset_console_outbox()
    await svc.request_password_reset("reset-me@example.com")

    assert len(email_svc._console_outbox) == 1
    body_text = email_svc._console_outbox[0]["body_text"]
    url = _extract_url_from_text(body_text)
    token = url.split("token=")[-1]

    result = await svc.complete_password_reset(token, "new-pass-456!")
    assert result is True

    row_after = await db.fetchrow(
        "SELECT password_hash FROM users WHERE id = %s", str(user_id)
    )
    new_hash = row_after["password_hash"]

    # Hash must have changed.
    assert new_hash != old_hash
    # New password verifies against the new hash.
    assert ph.verify(new_hash, "new-pass-456!")
    # Old password no longer matches.
    from argon2.exceptions import VerifyMismatchError
    with pytest.raises(VerifyMismatchError):
        ph.verify(new_hash, "old-pass!")
