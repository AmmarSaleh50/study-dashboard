"""Smoke test for app/intents/lectures.py — proves the pass-through works.

Phase 2 will replace these with real per-user-scoping tests.
"""
import pytest
from uuid import UUID

OPERATOR = UUID("00000000-0000-0000-0000-000000000001")


@pytest.mark.asyncio
async def test_lectures_intent_create_then_mark_attended(client, db_conn):
    from app.intents import courses as course_intent
    from app.intents import lectures as intent
    from app.schemas import CourseCreate, LectureCreate

    await course_intent.create_course(OPERATOR, CourseCreate(code="LECC", full_name="Lecture Course"))
    lec = await intent.create_lecture(
        OPERATOR,
        LectureCreate(course_code="LECC", number=1, held_on="2026-01-10", kind="lecture"),
    )
    assert lec.course_code == "LECC"
    assert lec.attended is False

    updated = await intent.mark_attended(OPERATOR, str(lec.id), True)
    assert updated.attended is True
