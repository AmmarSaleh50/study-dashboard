"""Tests for the User-returning auth dependencies (require_user / optional_user).

Phase 0: returns the sentinel User regardless of cookie identity (single-tenant).
Phase 1: will look up the user from the session cookie's signed payload.
"""
import pytest
from uuid import UUID


@pytest.mark.asyncio
async def test_optional_user_no_cookie_returns_none(client):
    """optional_user should return None when no session cookie is present."""
    from app.auth import optional_user
    result = await optional_user(study_session=None)
    assert result is None


@pytest.mark.asyncio
async def test_require_user_returns_sentinel_when_authed(client, monkeypatch):
    """require_user with a valid cookie returns the sentinel User."""
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
