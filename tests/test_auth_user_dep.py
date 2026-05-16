"""Tests for the User-returning auth dependencies (require_user / optional_user).

Phase 3: cookie payload carries user_id; require_user hits the users table.
Legacy `b"authed"` cookies fall back to the sentinel user (migration grace).
"""
import pytest


@pytest.mark.asyncio
async def test_optional_user_no_cookie_returns_none(client):
    """optional_user should return None when no session cookie is present."""
    from app.auth import optional_user
    result = await optional_user(study_session=None)
    assert result is None


@pytest.mark.asyncio
async def test_require_user_returns_sentinel_when_authed(client, monkeypatch):
    """Legacy cookie path: a cookie signed `b"authed"` (pre-Phase-3) still
    resolves to the sentinel user via the migration-grace fallback."""
    from app.auth import require_user, _signer, SENTINEL_USER_ID

    token = _signer().sign(b"authed").decode()
    user = await require_user(study_session=token)
    assert user.id == SENTINEL_USER_ID
    assert user.email == "operator@local"


@pytest.mark.asyncio
async def test_require_user_no_cookie_raises_401(client):
    """require_user without a cookie raises HTTP 401."""
    from fastapi import HTTPException
    from app.auth import require_user

    with pytest.raises(HTTPException) as exc:
        await require_user(study_session=None)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_sentinel_user_uses_env_overrides(monkeypatch):
    """OPERATOR_USER_ID + OPERATOR_EMAIL env vars override the sentinel defaults."""
    custom_uuid = "11111111-1111-1111-1111-111111111111"
    monkeypatch.setenv("OPERATOR_USER_ID", custom_uuid)
    monkeypatch.setenv("OPERATOR_EMAIL", "admin@example.test")
    monkeypatch.setenv("OPERATOR_DISPLAY_NAME", "Custom Admin")
    from app.config import get_settings
    from app.auth import _sentinel_user
    get_settings.cache_clear()
    _sentinel_user.cache_clear()
    u = _sentinel_user()
    assert str(u.id) == custom_uuid
    assert u.email == "admin@example.test"
    assert u.display_name == "Custom Admin"
    # Restore caches so later tests see the default sentinel UUID.
    get_settings.cache_clear()
    _sentinel_user.cache_clear()


@pytest.mark.asyncio
async def test_require_user_returns_db_user_from_new_cookie_payload(client, db_conn):
    """The new cookie payload carries user_id; require_user looks up users table."""
    from app.auth import require_user, _signer, SENTINEL_USER_ID
    import json
    import time

    # The sentinel user already exists in the DB (seeded by Phase 1 migration).
    payload = json.dumps({"u": str(SENTINEL_USER_ID), "iat": int(time.time())}).encode()
    token = _signer().sign(payload).decode()

    user = await require_user(study_session=token)
    assert user.id == SENTINEL_USER_ID
    assert user.email == "operator@local"


@pytest.mark.asyncio
async def test_require_user_unknown_user_id_in_cookie_raises_401(client, db_conn):
    """A signed cookie with a user_id that doesn't exist in users → 401."""
    from fastapi import HTTPException
    from app.auth import require_user, _signer
    import json
    import time
    from uuid import uuid4

    unknown = str(uuid4())
    payload = json.dumps({"u": unknown, "iat": int(time.time())}).encode()
    token = _signer().sign(payload).decode()

    with pytest.raises(HTTPException) as exc:
        await require_user(study_session=token)
    assert exc.value.status_code == 401
