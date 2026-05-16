"""TOTP state I/O.

Single home for the SQL that reads/writes the TOTP secret + enabled flag.
Phase 0: persisted to app_settings (singleton row, id=1).
Phase 1: app_settings is keyed by user_id; uses SENTINEL_USER_ID.
"""
from typing import Optional

from .. import db
from ..auth import SENTINEL_USER_ID


async def get_state() -> tuple[bool, Optional[str]]:
    """Return (totp_enabled, totp_secret) for the current operator/user."""
    try:
        row = await db.fetchrow(
            "SELECT totp_enabled, totp_secret FROM app_settings WHERE user_id = %s LIMIT 1",
            SENTINEL_USER_ID,
        )
        if row:
            return bool(row.get("totp_enabled")), row.get("totp_secret")
    except Exception:
        pass
    return False, None


async def set_pending(secret: str) -> None:
    """Store a fresh secret with totp_enabled=false (idempotent upsert)."""
    await db.execute(
        "INSERT INTO app_settings (user_id, totp_secret, totp_enabled) "
        "VALUES (%s, %s, false) "
        "ON CONFLICT (user_id) DO UPDATE "
        "SET totp_secret = EXCLUDED.totp_secret, totp_enabled = false",
        SENTINEL_USER_ID, secret,
    )


async def enable() -> None:
    await db.execute(
        "UPDATE app_settings SET totp_enabled = true WHERE user_id = %s",
        SENTINEL_USER_ID,
    )


async def disable() -> None:
    await db.execute(
        "UPDATE app_settings SET totp_enabled = false, totp_secret = NULL WHERE user_id = %s",
        SENTINEL_USER_ID,
    )
