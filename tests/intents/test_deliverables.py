"""Smoke test for app/intents/deliverables.py — proves the pass-through works.

Phase 2 will replace these with real per-user-scoping tests.
"""
import pytest
from uuid import UUID

OPERATOR = UUID("00000000-0000-0000-0000-000000000001")


@pytest.mark.asyncio
async def test_deliverables_intent_create_and_submit(client, db_conn):
    from app.intents import courses as course_intent
    from app.intents import deliverables as intent
    from app.schemas import CourseCreate, DeliverableCreate

    await course_intent.create_course(OPERATOR, CourseCreate(code="DELC", full_name="Deliverable Course"))
    deliv = await intent.create_deliverable(
        OPERATOR,
        DeliverableCreate(course_code="DELC", name="HW 1", kind="submission", due_at="2026-06-01T12:00:00Z"),
    )
    assert deliv.course_code == "DELC"
    assert deliv.status == "open"

    submitted = await intent.mark_submitted(OPERATOR, str(deliv.id))
    assert submitted.status == "submitted"

    reopened = await intent.reopen_deliverable(OPERATOR, str(deliv.id))
    assert reopened.status == "open"
