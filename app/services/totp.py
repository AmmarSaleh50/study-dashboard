"""TOTP state I/O.

Single home for the SQL that reads/writes the TOTP secret + enabled flag.
Phase 0: persists to app_settings (singleton row, id=1).
Phase 1: will switch to users.totp_* — one-file change here, callers
stay untouched.
"""
from typing import Optional

from .. import db


async def get_state() -> tuple[bool, Optional[str]]:
    """Return (totp_enabled, totp_secret) for the current operator/user."""
    try:
        row = await db.fetchrow(
            "SELECT totp_enabled, totp_secret FROM app_settings WHERE id = 1 LIMIT 1"
        )
        if row:
            return bool(row.get("totp_enabled")), row.get("totp_secret")
    except Exception:
        pass
    return False, None


async def set_pending(secret: str) -> None:
    """Store a fresh secret with totp_enabled=false (idempotent upsert)."""
    await db.execute(
        "INSERT INTO app_settings (id, totp_secret, totp_enabled) "
        "VALUES (1, %s, false) "
        "ON CONFLICT (id) DO UPDATE "
        "SET totp_secret = EXCLUDED.totp_secret, totp_enabled = false",
        secret,
    )


async def enable() -> None:
    await db.execute("UPDATE app_settings SET totp_enabled = true WHERE id = 1")


async def disable() -> None:
    await db.execute(
        "UPDATE app_settings SET totp_enabled = false, totp_secret = NULL WHERE id = 1"
    )
