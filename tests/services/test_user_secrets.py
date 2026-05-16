import pytest
from uuid import UUID
from cryptography.fernet import Fernet


@pytest.fixture(autouse=True)
def _enc_key(monkeypatch):
    """Every test needs SECRETS_ENCRYPTION_KEY set for Fernet round-trips."""
    monkeypatch.setenv("SECRETS_ENCRYPTION_KEY", Fernet.generate_key().decode())
    from app.config import get_settings
    get_settings.cache_clear()


OPERATOR = UUID("00000000-0000-0000-0000-000000000001")


@pytest.mark.asyncio
async def test_get_secrets_missing_returns_empty(client, db_conn):
    from app.services import user_secrets as svc
    sec = await svc.get_secrets(OPERATOR)
    assert sec.telegram_bot_token is None
    assert sec.telegram_chat_id is None
    assert sec.telegram_webhook_secret is None


@pytest.mark.asyncio
async def test_update_then_get_roundtrip(client, db_conn):
    from app.services import user_secrets as svc
    await svc.update_secrets(
        OPERATOR,
        telegram_bot_token="bot:abc123",
        telegram_chat_id="-1001234567",
        telegram_webhook_secret="wh-sec",
    )
    sec = await svc.get_secrets(OPERATOR)
    assert sec.telegram_bot_token == "bot:abc123"
    assert sec.telegram_chat_id == "-1001234567"
    assert sec.telegram_webhook_secret == "wh-sec"


@pytest.mark.asyncio
async def test_update_partial_preserves_other_fields(client, db_conn):
    from app.services import user_secrets as svc
    await svc.update_secrets(OPERATOR, telegram_bot_token="t1", telegram_chat_id="c1")
    await svc.update_secrets(OPERATOR, telegram_chat_id="c2")  # only chat_id
    sec = await svc.get_secrets(OPERATOR)
    assert sec.telegram_bot_token == "t1"  # unchanged
    assert sec.telegram_chat_id == "c2"


@pytest.mark.asyncio
async def test_clear_flag_nulls_the_column(client, db_conn):
    from app.services import user_secrets as svc
    await svc.update_secrets(OPERATOR, telegram_bot_token="t1", telegram_chat_id="c1")
    await svc.update_secrets(OPERATOR, clear_telegram_bot_token=True)
    sec = await svc.get_secrets(OPERATOR)
    assert sec.telegram_bot_token is None
    assert sec.telegram_chat_id == "c1"  # preserved


@pytest.mark.asyncio
async def test_get_user_id_by_chat_id(client, db_conn):
    from app.services import user_secrets as svc
    await svc.update_secrets(OPERATOR, telegram_chat_id="-1009999")
    found = await svc.get_user_id_by_chat_id("-1009999")
    assert found == OPERATOR


@pytest.mark.asyncio
async def test_get_user_id_by_chat_id_unknown_returns_none(client, db_conn):
    from app.services import user_secrets as svc
    assert await svc.get_user_id_by_chat_id("-999999") is None
