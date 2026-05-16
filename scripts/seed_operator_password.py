#!/usr/bin/env python3
"""Seed / reconcile the operator user from .env vars.

Reads from the container's env (`env_file: .env`):
  - OPERATOR_USER_ID    — UUID of the operator row. Defaults to the migration's
                          placeholder UUID. Self-hosters may pick a fresh one
                          via `uuidgen` and set it here.
  - OPERATOR_EMAIL      — email address used to log in.
  - OPERATOR_DISPLAY_NAME — friendly name shown in the UI.
  - APP_PASSWORD_HASH   — argon2id hash from `uv run python -m app.tools.hashpw 'your-password'`.

Idempotent. Safe to run on every deploy. Only updates fields that the env
provides; leaves the rest alone.

Behaviour:
  - If OPERATOR_USER_ID's row doesn't exist (e.g. operator changed the UUID),
    INSERT it.
  - Always UPDATE email + display_name when those env vars are set.
  - Set password_hash only if APP_PASSWORD_HASH is provided AND the existing
    hash is NULL (avoid clobbering a password the operator changed via the UI).
"""
from __future__ import annotations
import asyncio
import os
import sys


async def main() -> int:
    op_user_id = os.environ.get(
        "OPERATOR_USER_ID", "00000000-0000-0000-0000-000000000001"
    ).strip()
    op_email = os.environ.get("OPERATOR_EMAIL", "").strip().lower()
    op_display = os.environ.get("OPERATOR_DISPLAY_NAME", "").strip()
    app_pw_hash = os.environ.get("APP_PASSWORD_HASH", "").strip()

    if not op_email:
        print(
            "OPERATOR_EMAIL not set in .env — skipping operator seed. "
            "Set it to your login email and redeploy."
        )
        return 0

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from app import db as db_module

    await db_module.init_pool()
    try:
        existing = await db_module.fetchrow(
            "SELECT id, email, display_name, password_hash FROM users WHERE id = %s",
            op_user_id,
        )

        if existing is None:
            # Operator picked a new UUID; create the row.
            await db_module.execute(
                "INSERT INTO users (id, email, display_name, password_hash) "
                "VALUES (%s, %s, %s, %s) "
                "ON CONFLICT (id) DO NOTHING",
                op_user_id,
                op_email,
                op_display or "Operator",
                app_pw_hash or None,
            )
            print(
                f"created operator row id={op_user_id} email={op_email} "
                f"display_name={op_display or 'Operator'!r} "
                f"password_hash={'set' if app_pw_hash else 'NULL'}"
            )
            return 0

        # Reconcile existing row with env.
        updates: list[str] = []
        values: list[str] = []
        if existing.get("email") != op_email:
            updates.append("email = %s")
            values.append(op_email)
        if op_display and existing.get("display_name") != op_display:
            updates.append("display_name = %s")
            values.append(op_display)
        if app_pw_hash and not existing.get("password_hash"):
            updates.append("password_hash = %s")
            values.append(app_pw_hash)

        if not updates:
            print(f"operator {op_user_id} already matches .env — nothing to do")
            return 0

        values.append(op_user_id)
        sql = f"UPDATE users SET {', '.join(updates)} WHERE id = %s"
        await db_module.execute(sql, *values)
        print(
            f"updated operator {op_user_id}: " + ", ".join(
                u.split(" = ")[0] for u in updates
            )
        )
        return 0
    finally:
        await db_module.close_pool()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
