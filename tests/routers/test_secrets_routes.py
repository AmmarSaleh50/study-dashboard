"""HTTP endpoint tests for GET/PATCH /api/settings/secrets and POST
/api/settings/telegram/test.

Covers:
1. GET returns booleans (never decrypted strings) for an empty user.
2. GET reflects what PATCH set (token/webhook return as `*_set: true`,
   chat_id passes through plaintext since it isn't secret).
3. PATCH supports empty-string clear semantics per-field.
4. PATCH with only one field leaves the others alone.
5. POST /telegram/test with no creds → ok=false with a helpful message.
6. POST /telegram/test with creds + a 200 from Telegram → ok=true; httpx
   call is mocked so we don't hit the real API.
"""
from unittest.mock import AsyncMock, patch

import pytest
from cryptography.fernet import Fernet

from app.auth import _sentinel_user, require_user
from app.main import create_app


@pytest.fixture(autouse=True)
def _enc_key(monkeypatch):
    """Every test needs SECRETS_ENCRYPTION_KEY set for Fernet round-trips."""
    monkeypatch.setenv("SECRETS_ENCRYPTION_KEY", Fernet.generate_key().decode())
    from app.config import get_settings
    get_settings.cache_clear()


@pytest.fixture
def authed_client(db_conn, monkeypatch):
    """An httpx AsyncClient whose `require_user` always resolves to the
    sentinel operator user — bypasses cookie auth for endpoint testing.
    """
    from httpx import ASGITransport, AsyncClient
    import app.db as db_module

    monkeypatch.setattr(db_module, "_pool", db_conn)
    app = create_app()
    app.dependency_overrides[require_user] = lambda: _sentinel_user()
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_get_secrets_empty_returns_all_false(authed_client, db_conn):
    """No user_secrets row → all booleans false, chat_id None."""
    async with authed_client as ac:
        resp = await ac.get("/api/settings/secrets")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body == {
        "telegram_bot_token_set": False,
        "telegram_chat_id": None,
        "telegram_webhook_secret_set": False,
    }
    # Crucially, no decrypted token strings ever leak in this payload.
    assert "telegram_bot_token" not in body
    assert "telegram_webhook_secret" not in body


@pytest.mark.asyncio
async def test_patch_set_then_get_reflects_set_state(authed_client, db_conn):
    """PATCH with all three fields sets them; GET shows booleans + chat_id."""
    async with authed_client as ac:
        resp = await ac.patch(
            "/api/settings/secrets",
            json={
                "telegram_bot_token": "bot:abc123",
                "telegram_chat_id": "-1001234567",
                "telegram_webhook_secret": "wh-sec",
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["telegram_bot_token_set"] is True
        assert body["telegram_chat_id"] == "-1001234567"
        assert body["telegram_webhook_secret_set"] is True

        # GET round-trip — booleans (no plaintext token leak).
        resp2 = await ac.get("/api/settings/secrets")
    assert resp2.status_code == 200, resp2.text
    assert resp2.json() == {
        "telegram_bot_token_set": True,
        "telegram_chat_id": "-1001234567",
        "telegram_webhook_secret_set": True,
    }


@pytest.mark.asyncio
async def test_patch_empty_string_clears_field(authed_client, db_conn):
    """PATCH telegram_bot_token="" clears it; other fields preserved."""
    async with authed_client as ac:
        # Seed.
        await ac.patch(
            "/api/settings/secrets",
            json={
                "telegram_bot_token": "bot:abc",
                "telegram_chat_id": "12345",
                "telegram_webhook_secret": "wh1",
            },
        )
        # Clear only the bot token.
        resp = await ac.patch(
            "/api/settings/secrets",
            json={"telegram_bot_token": ""},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
    assert body["telegram_bot_token_set"] is False
    assert body["telegram_chat_id"] == "12345"            # preserved
    assert body["telegram_webhook_secret_set"] is True    # preserved


@pytest.mark.asyncio
async def test_patch_partial_only_touches_specified_field(authed_client, db_conn):
    """PATCH with only chat_id leaves token + webhook untouched."""
    async with authed_client as ac:
        await ac.patch(
            "/api/settings/secrets",
            json={
                "telegram_bot_token": "bot:abc",
                "telegram_chat_id": "12345",
                "telegram_webhook_secret": "wh1",
            },
        )
        resp = await ac.patch(
            "/api/settings/secrets",
            json={"telegram_chat_id": "67890"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
    assert body["telegram_bot_token_set"] is True       # unchanged
    assert body["telegram_chat_id"] == "67890"          # changed
    assert body["telegram_webhook_secret_set"] is True  # unchanged


@pytest.mark.asyncio
async def test_telegram_test_without_creds_returns_ok_false(authed_client, db_conn):
    """POST /telegram/test with no token configured → ok=false, helpful msg."""
    async with authed_client as ac:
        resp = await ac.post("/api/settings/telegram/test")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is False
    assert body["message"] and "token" in body["message"].lower()


@pytest.mark.asyncio
async def test_telegram_test_with_creds_sends_message(authed_client, db_conn):
    """POST /telegram/test with creds set → mocks httpx and asserts ok=true."""
    async with authed_client as ac:
        # Configure creds.
        await ac.patch(
            "/api/settings/secrets",
            json={
                "telegram_bot_token": "bot:xyz",
                "telegram_chat_id": "55555",
            },
        )

        # Stub the httpx POST so we don't hit api.telegram.org for real.
        class _R:
            status_code = 200
            def json(self):
                return {"ok": True}

        with patch("app.routers.settings.httpx.AsyncClient") as mock_cls:
            mock_inst = mock_cls.return_value.__aenter__.return_value
            mock_inst.post = AsyncMock(return_value=_R())
            resp = await ac.post("/api/settings/telegram/test")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True

    # Verify the call shape: URL contains the bot token, body has chat_id + text.
    mock_inst.post.assert_called_once()
    call = mock_inst.post.call_args
    url = call.args[0]
    assert "bot:xyz" in url
    payload = call.kwargs["json"]
    assert payload["chat_id"] == "55555"
    assert "OpenStudy" in payload["text"]
