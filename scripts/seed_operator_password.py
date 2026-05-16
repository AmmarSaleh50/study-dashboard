#!/usr/bin/env python3
"""Seed the operator user's password_hash from APP_PASSWORD_HASH env var.

Run after `db push` during deploy. Idempotent — only sets the hash if it's NULL.
Lets self-host upgraders move from the env-only password to the per-user
users.password_hash without losing access.
"""
from __future__ import annotations
import asyncio
import os
import sys


async def main() -> int:
    app_pw_hash = os.environ.get("APP_PASSWORD_HASH", "").strip()
    op_user_id = os.environ.get("OPERATOR_USER_ID", "00000000-0000-0000-0000-000000000001").strip()
    if not app_pw_hash:
        print("APP_PASSWORD_HASH not set — skipping operator password seed")
        return 0

    # Import lazily so the script works even if app deps aren't fully loaded.
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from app import db as db_module

    await db_module.init_pool()
    try:
        row = await db_module.fetchrow(
            "SELECT password_hash FROM users WHERE id = %s",
            op_user_id,
        )
        if not row:
            print(f"operator user {op_user_id} not in users table — did migration 020001 run?")
            return 1
        if row.get("password_hash"):
            print(f"operator {op_user_id} already has password_hash — skipping")
            return 0

        await db_module.execute(
            "UPDATE users SET password_hash = %s WHERE id = %s",
            app_pw_hash, op_user_id,
        )
        print(f"seeded operator {op_user_id} password_hash from APP_PASSWORD_HASH env")
        return 0
    finally:
        await db_module.close_pool()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
