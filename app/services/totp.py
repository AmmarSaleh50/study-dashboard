"""TOTP state I/O — per-user storage.

Phase 1: TOTP moved from app_settings.totp_* to users.totp_*.
Phase 2: hardcoded SENTINEL_USER_ID becomes a real user_id parameter.
"""
from typing import Optional

from .. import db
from ..auth import SENTINEL_USER_ID


async def get_state() -> tuple[bool, Optional[str]]:
    """Return (totp_enabled, totp_secret) for the operator user."""
    try:
        row = await db.fetchrow(
            "SELECT totp_enabled, totp_secret FROM users WHERE id = %s LIMIT 1",
            SENTINEL_USER_ID,
        )
        if row:
            return bool(row.get("totp_enabled")), row.get("totp_secret")
    except Exception:
        pass
    return False, None


async def set_pending(secret: str) -> None:
    """Store a fresh secret with totp_enabled=false.

    The users row always exists (created by the users-table migration's
    seed), so a plain UPDATE suffices — no upsert needed.
    """
    await db.execute(
        "UPDATE users SET totp_secret = %s, totp_enabled = false WHERE id = %s",
        secret, SENTINEL_USER_ID,
    )


async def enable() -> None:
    await db.execute(
        "UPDATE users SET totp_enabled = true WHERE id = %s",
        SENTINEL_USER_ID,
    )


async def disable() -> None:
    await db.execute(
        "UPDATE users SET totp_enabled = false, totp_secret = NULL WHERE id = %s",
        SENTINEL_USER_ID,
    )
