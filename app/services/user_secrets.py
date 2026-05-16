"""Per-user encrypted secrets (Telegram first; future Moodle, Stripe, etc.).

The `*_enc` columns hold Fernet ciphertext; the service encrypts on write
and decrypts on read using app/services/secrets.py.
"""
from dataclasses import dataclass
from typing import Optional
from uuid import UUID

from .. import db
from . import secrets as secrets_svc


@dataclass(frozen=True)
class UserSecrets:
    user_id: UUID
    telegram_bot_token: Optional[str]
    telegram_chat_id: Optional[str]
    telegram_webhook_secret: Optional[str]


async def get_secrets(user_id: UUID) -> UserSecrets:
    """Return decrypted secrets for the user. NULL columns → None fields."""
    row = await db.fetchrow(
        "SELECT user_id, telegram_bot_token_enc, telegram_chat_id, telegram_webhook_secret_enc "
        "FROM user_secrets WHERE user_id = %s",
        str(user_id),
    )
    if not row:
        return UserSecrets(user_id=user_id, telegram_bot_token=None,
                           telegram_chat_id=None, telegram_webhook_secret=None)
    bot_token_enc = row.get("telegram_bot_token_enc")
    webhook_secret_enc = row.get("telegram_webhook_secret_enc")
    return UserSecrets(
        user_id=user_id,
        telegram_bot_token=secrets_svc.decrypt(bytes(bot_token_enc)) if bot_token_enc else None,
        telegram_chat_id=row.get("telegram_chat_id"),
        telegram_webhook_secret=secrets_svc.decrypt(bytes(webhook_secret_enc)) if webhook_secret_enc else None,
    )


async def update_secrets(
    user_id: UUID,
    *,
    telegram_bot_token: Optional[str] = None,
    telegram_chat_id: Optional[str] = None,
    telegram_webhook_secret: Optional[str] = None,
    clear_telegram_bot_token: bool = False,
    clear_telegram_webhook_secret: bool = False,
    clear_telegram_chat_id: bool = False,
) -> None:
    """Upsert per-user secrets. Pass a *_token=str to set; clear_*=True to NULL."""
    # Build the field updates dict.
    updates = {}
    if telegram_bot_token is not None:
        updates["telegram_bot_token_enc"] = secrets_svc.encrypt(telegram_bot_token)
    elif clear_telegram_bot_token:
        updates["telegram_bot_token_enc"] = None
    if telegram_chat_id is not None:
        updates["telegram_chat_id"] = telegram_chat_id
    elif clear_telegram_chat_id:
        updates["telegram_chat_id"] = None
    if telegram_webhook_secret is not None:
        updates["telegram_webhook_secret_enc"] = secrets_svc.encrypt(telegram_webhook_secret)
    elif clear_telegram_webhook_secret:
        updates["telegram_webhook_secret_enc"] = None

    if not updates:
        return  # nothing to do

    # Upsert: INSERT row if missing; UPDATE columns if present.
    cols = list(updates.keys())
    placeholders = ", ".join(["%s"] * (1 + len(cols)))  # user_id + each value
    set_clause = ", ".join([f"{c} = EXCLUDED.{c}" for c in cols])
    sql = (
        f"INSERT INTO user_secrets (user_id, {', '.join(cols)}, updated_at) "
        f"VALUES ({placeholders}, now()) "
        f"ON CONFLICT (user_id) DO UPDATE SET {set_clause}, updated_at = now()"
    )
    values = [str(user_id), *updates.values()]
    await db.execute(sql, *values)


async def get_user_id_by_chat_id(chat_id: str) -> Optional[UUID]:
    """Lookup the user owning a given Telegram chat_id. Used by the webhook router."""
    row = await db.fetchrow(
        "SELECT user_id FROM user_secrets WHERE telegram_chat_id = %s",
        chat_id,
    )
    if not row:
        return None
    val = row["user_id"]
    return val if isinstance(val, UUID) else UUID(val)
