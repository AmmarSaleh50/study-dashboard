import pytest
import pyotp


@pytest.mark.asyncio
async def test_get_state_when_totp_disabled(client, db_conn):
    from app.services import totp as svc
    # Fresh seed: users row exists but totp_secret is NULL and totp_enabled is false.
    # get_state should return defaults (False, None).
    enabled, secret = await svc.get_state()
    assert enabled is False
    assert secret is None


@pytest.mark.asyncio
async def test_set_pending_upserts_and_clears_enabled(client, db_conn):
    from app.services import totp as svc
    new_secret = pyotp.random_base32()
    await svc.set_pending(new_secret)
    enabled, secret = await svc.get_state()
    assert enabled is False
    assert secret == new_secret


@pytest.mark.asyncio
async def test_enable_flips_totp_enabled(client, db_conn):
    from app.services import totp as svc
    new_secret = pyotp.random_base32()
    await svc.set_pending(new_secret)
    await svc.enable()
    enabled, secret = await svc.get_state()
    assert enabled is True
    assert secret == new_secret


@pytest.mark.asyncio
async def test_disable_clears_secret_and_flag(client, db_conn):
    from app.services import totp as svc
    await svc.set_pending(pyotp.random_base32())
    await svc.enable()
    await svc.disable()
    enabled, secret = await svc.get_state()
    assert enabled is False
    assert secret is None
