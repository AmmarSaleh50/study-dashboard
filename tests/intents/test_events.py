"""Smoke test for app/intents/events.py — proves the pass-through works.

Phase 2 will replace these with real per-user-scoping tests.
"""
import pytest
from uuid import UUID

OPERATOR = UUID("00000000-0000-0000-0000-000000000001")


@pytest.mark.asyncio
async def test_events_intent_record_then_list(client, db_conn):
    from app.intents import events as intent
    from app.schemas import EventCreate

    event = await intent.record_event(OPERATOR, EventCreate(kind="test_intent_smoke"))
    assert event.kind == "test_intent_smoke"

    lst = await intent.list_events(OPERATOR, kind="test_intent_smoke")
    assert len(lst) >= 1
    assert lst[0].kind == "test_intent_smoke"
