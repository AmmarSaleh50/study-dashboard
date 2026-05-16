"""Webhook routing tests for POST /internal/telegram — Phase 6 multi-user dispatch.

Three scenarios:
1. Known chat_id (found in user_secrets) → dispatches as that user.
2. Unknown chat_id but matches TELEGRAM_CHAT_ID env → operator-legacy sentinel.
3. Unknown chat_id and no env match → 403.
"""
import os
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest


WEBHOOK_SECRET = "test-webhook-secret"
KNOWN_CHAT_ID = 11111
OPERATOR_CHAT_ID = 22222
UNKNOWN_CHAT_ID = 99999
KNOWN_USER_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


def _make_tg_body(chat_id: int, text: str = "/help") -> dict:
    return {
        "message": {
            "chat": {"id": chat_id},
            "text": text,
        }
    }


def _headers() -> dict:
    return {"X-Telegram-Bot-Api-Secret-Token": WEBHOOK_SECRET}


@pytest.fixture(autouse=True)
def _patch_env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", WEBHOOK_SECRET)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", str(OPERATOR_CHAT_ID))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "env-token")
    # Avoid real HTTP calls for sendMessage.
    monkeypatch.setenv("N8N_MOODLE_WEBHOOK_URL", "")


@pytest.mark.asyncio
async def test_known_chat_id_dispatches_as_that_user(client, db_conn, monkeypatch):
    """A chat_id present in user_secrets is resolved to that user_id."""
    # Patch user_secrets lookup to return KNOWN_USER_ID.
    with (
        patch(
            "app.services.user_secrets.get_user_id_by_chat_id",
            new=AsyncMock(return_value=KNOWN_USER_ID),
        ),
        patch(
            "app.services.user_secrets.get_secrets",
            new=AsyncMock(return_value=type("S", (), {"telegram_bot_token": "user-token"})()),
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
    # Reply was sent (send_message called with user-token or env-token).
    mock_send.assert_called_once()
    call_args = mock_send.call_args
    # First positional arg is the token — should come from user_secrets.
    assert call_args.args[0] == "user-token"
    assert call_args.args[1] == KNOWN_CHAT_ID


@pytest.mark.asyncio
async def test_operator_legacy_chat_id_uses_sentinel(client, db_conn, monkeypatch):
    """Unknown chat_id matching TELEGRAM_CHAT_ID env → uses sentinel user."""
    with (
        patch(
            "app.services.user_secrets.get_user_id_by_chat_id",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "app.services.user_secrets.get_secrets",
            new=AsyncMock(return_value=type("S", (), {"telegram_bot_token": None})()),
        ),
        patch("app.services.telegram.send_message", new=AsyncMock()) as mock_send,
    ):
        resp = await client.post(
            "/api/internal/telegram",
            json=_make_tg_body(OPERATOR_CHAT_ID, "/status"),
            headers=_headers(),
        )

    assert resp.status_code == 200, resp.text
    assert resp.json()["ok"] is True
    # Reply must have been sent (env token used as fallback).
    mock_send.assert_called_once()
    assert mock_send.call_args.args[0] == "env-token"


@pytest.mark.asyncio
async def test_unknown_chat_id_returns_403(client, db_conn, monkeypatch):
    """A chat_id not in user_secrets and not matching env → 403."""
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
    assert "chat_id not registered" in resp.json()["detail"]
