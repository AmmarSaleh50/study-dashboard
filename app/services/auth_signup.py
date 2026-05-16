"""Signup, email-verification, and password-reset flows.

All token operations are idempotent / silent where possible — callers should
never reveal whether a given email address is registered.
"""
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from argon2 import PasswordHasher

from .. import db
from ..config import get_settings
from . import email as email_svc

_ph = PasswordHasher()


async def signup(email: str, password: str) -> UUID:
    """Create a user with email_verified_at = NULL. Mints + sends a
    verification token. Returns the new user_id.

    Idempotent for already-registered emails: if a user with this email
    already exists, returns their id without re-sending (caller can
    re-request verification via request_resend_verification if added later).
    Raises ValueError if SIGNUPS_ENABLED is false.
    """
    s = get_settings()
    if not s.signups_enabled:
        raise ValueError("signups disabled")

    email = email.strip().lower()
    if "@" not in email or len(email) > 254:
        raise ValueError("invalid email")

    # Check for existing user.
    existing = await db.fetchrow(
        "SELECT id, email_verified_at FROM users WHERE email = %s", email
    )
    if existing:
        # Don't reveal whether the email is taken — caller treats this as success.
        # If unverified, optionally re-send verification (skipped for now).
        return UUID(existing["id"])

    user_id = uuid4()
    password_hash = _ph.hash(password)

    async with db.db() as conn, conn.cursor() as cur:
        await cur.execute(
            "INSERT INTO users (id, email, password_hash, display_name) VALUES (%s, %s, %s, %s)",
            (str(user_id), email, password_hash, email.split("@")[0]),
        )
        token = secrets.token_urlsafe(32)
        expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
        await cur.execute(
            "INSERT INTO email_verifications (token, user_id, expires_at) VALUES (%s, %s, %s)",
            (token, str(user_id), expires_at),
        )

    # Send verification email outside the transaction.
    verify_url = f"{s.public_url.rstrip('/')}/verify-email?token={token}"
    txt, html = email_svc.render("verify_email", {"verify_url": verify_url})
    await email_svc.send_email(
        to=email,
        subject="Verify your OpenStudy email",
        body_text=txt,
        body_html=html,
    )
    return user_id


async def verify_email(token: str) -> bool:
    """Mark the token used and set users.email_verified_at. Returns True on success.

    Returns False if the token doesn't exist, is expired, or has been used.
    """
    row = await db.fetchrow(
        "SELECT user_id, expires_at, used_at FROM email_verifications WHERE token = %s",
        token,
    )
    if not row:
        return False
    if row["used_at"] is not None:
        return False
    if row["expires_at"] < datetime.now(timezone.utc):
        return False

    async with db.db() as conn, conn.cursor() as cur:
        await cur.execute(
            "UPDATE email_verifications SET used_at = now() WHERE token = %s",
            (token,),
        )
        await cur.execute(
            "UPDATE users SET email_verified_at = now() WHERE id = %s",
            (str(row["user_id"]),),
        )
    return True


async def request_password_reset(email: str) -> None:
    """Send a password-reset email if the address belongs to a user.
    Always returns silently (no user enumeration)."""
    s = get_settings()
    email = email.strip().lower()
    row = await db.fetchrow("SELECT id FROM users WHERE email = %s", email)
    if not row:
        return  # silent success

    user_id = row["id"]
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    await db.execute(
        "INSERT INTO password_resets (token, user_id, expires_at) VALUES (%s, %s, %s)",
        token,
        str(user_id),
        expires_at,
    )

    reset_url = f"{s.public_url.rstrip('/')}/reset-password?token={token}"
    txt, html = email_svc.render("password_reset", {"reset_url": reset_url})
    await email_svc.send_email(
        to=email,
        subject="Reset your OpenStudy password",
        body_text=txt,
        body_html=html,
    )


async def complete_password_reset(token: str, new_password: str) -> bool:
    """Set users.password_hash and mark the token used. Returns True on success."""
    row = await db.fetchrow(
        "SELECT user_id, expires_at, used_at FROM password_resets WHERE token = %s",
        token,
    )
    if not row:
        return False
    if row["used_at"] is not None:
        return False
    if row["expires_at"] < datetime.now(timezone.utc):
        return False

    new_hash = _ph.hash(new_password)
    async with db.db() as conn, conn.cursor() as cur:
        await cur.execute(
            "UPDATE password_resets SET used_at = now() WHERE token = %s",
            (token,),
        )
        await cur.execute(
            "UPDATE users SET password_hash = %s WHERE id = %s",
            (new_hash, str(row["user_id"])),
        )
    return True
