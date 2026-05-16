"""TOTP state I/O — per-user storage.

Phase 1: TOTP moved from app_settings.totp_* to users.totp_*.
Phase 2: hardcoded SENTINEL_USER_ID becomes a real user_id parameter.
"""
from typing import Optional
from uuid import UUID

from .. import db


async def get_state(user_id: UUID) -> tuple[bool, Optional[str]]:
    """Return (totp_enabled, totp_secret) for the given user."""
    try:
        row = await db.fetchrow(
            "SELECT totp_enabled, totp_secret FROM users WHERE id = %s LIMIT 1",
            user_id,
        )
        if row:
            return bool(row.get("totp_enabled")), row.get("totp_secret")
    except Exception:
        pass
    return False, None


async def set_pending(user_id: UUID, secret: str) -> None:
    """Store a fresh secret with totp_enabled=false.

    The users row always exists (created by the users-table migration's
    seed), so a plain UPDATE suffices — no upsert needed.
    """
    await db.execute(
        "UPDATE users SET totp_secret = %s, totp_enabled = false WHERE id = %s",
        secret, user_id,
    )


async def enable(user_id: UUID) -> None:
    await db.execute(
        "UPDATE users SET totp_enabled = true WHERE id = %s",
        user_id,
    )


async def disable(user_id: UUID) -> None:
    await db.execute(
        "UPDATE users SET totp_enabled = false, totp_secret = NULL WHERE id = %s",
        user_id,
    )
