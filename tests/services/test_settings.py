"""Tests for app/services/settings.py."""
import pytest


@pytest.mark.asyncio
async def test_get_settings_creates_singleton_if_missing(client, db_conn):
    from app.services import settings as svc
    result = await svc.get_settings()
    # AppSettings schema has no `id` field (extra="ignore"). Assert on
    # observable defaults of the singleton row instead.
    assert result.timezone == "UTC"
    assert result.locale == "en-US"
    # Confirm the row was actually persisted (not just defaults from schema).
    from app.auth import SENTINEL_USER_ID
    async with db_conn.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT count(*) AS n FROM app_settings WHERE user_id = %s",
            (SENTINEL_USER_ID,),
        )
        row = await cur.fetchone()
        assert row["n"] == 1


@pytest.mark.asyncio
async def test_update_settings_persists(client, db_conn):
    from app.schemas import AppSettingsPatch
    from app.services import settings as svc
    await svc.get_settings()  # ensure singleton exists
    updated = await svc.update_settings(AppSettingsPatch(display_name="Ammar"))
    assert updated.display_name == "Ammar"
    # Re-fetch to confirm persistence
    again = await svc.get_settings()
    assert again.display_name == "Ammar"


@pytest.mark.asyncio
async def test_update_settings_empty_patch_is_noop(client, db_conn):
    from app.schemas import AppSettingsPatch
    from app.services import settings as svc
    await svc.get_settings()
    original = (await svc.get_settings()).display_name
    result = await svc.update_settings(AppSettingsPatch())
    assert result.display_name == original
