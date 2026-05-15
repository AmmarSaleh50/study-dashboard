"""Smoke test for app/intents/slots.py — proves the pass-through works.

Phase 2 will replace these with real per-user-scoping tests.
"""
import pytest
from uuid import UUID

OPERATOR = UUID("00000000-0000-0000-0000-000000000001")


@pytest.mark.asyncio
async def test_slots_intent_create_then_list(client, db_conn):
    from app.intents import courses as course_intent
    from app.intents import slots as intent
    from app.schemas import CourseCreate, SlotCreate

    await course_intent.create_course(OPERATOR, CourseCreate(code="SLOTC", full_name="Slot Course"))
    slot = await intent.create_slot(
        OPERATOR,
        SlotCreate(course_code="SLOTC", weekday=1, start_time="09:00", end_time="10:00", kind="lecture"),
    )
    assert slot.course_code == "SLOTC"

    lst = await intent.list_slots(OPERATOR, course_code="SLOTC")
    assert len(lst) == 1
    assert lst[0].weekday == 1
