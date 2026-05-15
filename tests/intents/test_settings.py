"""Smoke test for app/intents/settings.py — proves the pass-through works.

Phase 2 will replace these with real per-user-scoping tests.
"""
import pytest
from uuid import UUID

OPERATOR = UUID("00000000-0000-0000-0000-000000000001")


@pytest.mark.asyncio
async def test_settings_intent_get_and_update(client, db_conn):
    from app.intents import settings as intent
    from app.schemas import AppSettingsPatch

    s = await intent.get_settings(OPERATOR)
    assert s is not None

    updated = await intent.update_settings(OPERATOR, AppSettingsPatch(display_name="Intent User"))
    assert updated.display_name == "Intent User"

    # Confirm get_settings reflects the update
    fetched = await intent.get_settings(OPERATOR)
    assert fetched.display_name == "Intent User"
