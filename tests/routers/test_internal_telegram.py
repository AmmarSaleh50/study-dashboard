"""Webhook routing tests for POST /internal/telegram — multi-tenant dispatch.

As of v0.7.0 the webhook has no env fallbacks. Each user owns:
  - chat_id (stored in user_secrets.telegram_chat_id)
  - webhook secret (stored in user_secrets.telegram_webhook_secret_enc)
  - bot token (stored in user_secrets.telegram_bot_token_enc)

The router:
  1. Resolves chat_id -> user_id via user_secrets.get_user_id_by_chat_id.
  2. Loads that user's secrets and verifies the inbound webhook-secret header.
  3. Dispatches the command under that user's contextvar.
  4. Replies via the user's own bot token (or drops the reply if absent).
"""
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest


KNOWN_CHAT_ID = 11111
UNKNOWN_CHAT_ID = 99999
KNOWN_USER_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
USER_WEBHOOK_SECRET = "per-user-secret"


def _make_tg_body(chat_id: int, text: str = "/help") -> dict:
    return {
        "message": {
            "chat": {"id": chat_id},
            "text": text,
        }
    }


def _headers(secret: str = USER_WEBHOOK_SECRET) -> dict:
    return {"X-Telegram-Bot-Api-Secret-Token": secret}


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    """Ensure any operator-legacy env vars are NOT set during tests — the
    router must rely solely on per-user user_secrets."""
    monkeypatch.delenv("TELEGRAM_WEBHOOK_SECRET", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.setenv("N8N_MOODLE_WEBHOOK_URL", "")


def _user_secrets_obj(
    *,
    bot_token: str | None = "user-token",
    webhook_secret: str | None = USER_WEBHOOK_SECRET,
):
    """Build a duck-typed user_secrets object the router can read."""
    return type(
        "S",
        (),
        {
            "telegram_bot_token": bot_token,
            "telegram_webhook_secret": webhook_secret,
        },
    )()


@pytest.mark.asyncio
async def test_known_chat_id_with_valid_secret_dispatches_and_replies(
    client, db_conn
):
    """A chat_id in user_secrets, paired with the right webhook secret,
    resolves to that user and the reply is sent via the user's bot token."""
    with (
        patch(
            "app.services.user_secrets.get_user_id_by_chat_id",
            new=AsyncMock(return_value=KNOWN_USER_ID),
        ),
        patch(
            "app.services.user_secrets.get_secrets",
            new=AsyncMock(return_value=_user_secrets_obj()),
        ),
        patch("app.services.telegram.send_message", new=AsyncMock()) as mock_send,
    ):
        resp = await client.post(
            "/api/internal/telegram",
            json=_make_tg_body(KNOWN_CHAT_ID, "/help"),
            headers=_headers(),
        )

    assert resp.status_code == 200, resp.text
    assert resp.json()["ok"] is True
    mock_send.assert_called_once()
    # First positional arg is the bot token — must come from user_secrets.
    assert mock_send.call_args.args[0] == "user-token"
    assert mock_send.call_args.args[1] == KNOWN_CHAT_ID


@pytest.mark.asyncio
async def test_known_chat_id_with_wrong_secret_returns_403(client, db_conn):
    """Inbound secret token that doesn't match the user's stored webhook
    secret → 403, even though the chat_id is registered."""
    with (
        patch(
            "app.services.user_secrets.get_user_id_by_chat_id",
            new=AsyncMock(return_value=KNOWN_USER_ID),
        ),
        patch(
            "app.services.user_secrets.get_secrets",
            new=AsyncMock(return_value=_user_secrets_obj()),
        ),
        patch("app.services.telegram.send_message", new=AsyncMock()) as mock_send,
    ):
        resp = await client.post(
            "/api/internal/telegram",
            json=_make_tg_body(KNOWN_CHAT_ID, "/help"),
            headers=_headers(secret="wrong-secret"),
        )

    assert resp.status_code == 403, resp.text
    assert "bad webhook token" in resp.json()["detail"]
    mock_send.assert_not_called()


@pytest.mark.asyncio
async def test_known_chat_id_with_no_stored_secret_returns_403(client, db_conn):
    """If the user has registered a chat_id but no webhook secret yet, the
    webhook must reject the call rather than fall back to anything."""
    with (
        patch(
            "app.services.user_secrets.get_user_id_by_chat_id",
            new=AsyncMock(return_value=KNOWN_USER_ID),
        ),
        patch(
            "app.services.user_secrets.get_secrets",
            new=AsyncMock(return_value=_user_secrets_obj(webhook_secret=None)),
        ),
    ):
        resp = await client.post(
            "/api/internal/telegram",
            json=_make_tg_body(KNOWN_CHAT_ID, "/help"),
            headers=_headers(),
        )

    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_unknown_chat_id_returns_403(client, db_conn):
    """A chat_id not present in user_secrets → 403 (no env fallback)."""
    with patch(
        "app.services.user_secrets.get_user_id_by_chat_id",
        new=AsyncMock(return_value=None),
    ):
        resp = await client.post(
            "/api/internal/telegram",
            json=_make_tg_body(UNKNOWN_CHAT_ID, "/help"),
            headers=_headers(),
        )

    assert resp.status_code == 403, resp.text
    assert "unknown telegram chat" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_reply_dropped_when_user_has_no_bot_token(client, db_conn):
    """Verified webhook, command dispatched, but user has no bot token →
    the reply is dropped silently (the request still returns 200)."""
    with (
        patch(
            "app.services.user_secrets.get_user_id_by_chat_id",
            new=AsyncMock(return_value=KNOWN_USER_ID),
        ),
        patch(
            "app.services.user_secrets.get_secrets",
            new=AsyncMock(return_value=_user_secrets_obj(bot_token=None)),
        ),
        patch("app.services.telegram.send_message", new=AsyncMock()) as mock_send,
    ):
        resp = await client.post(
            "/api/internal/telegram",
            json=_make_tg_body(KNOWN_CHAT_ID, "/help"),
            headers=_headers(),
        )

    assert resp.status_code == 200, resp.text
    mock_send.assert_not_called()
