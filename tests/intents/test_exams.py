"""Smoke test for app/intents/exams.py — proves the pass-through works.

Phase 2 will replace these with real per-user-scoping tests.
"""
import pytest
from uuid import UUID

OPERATOR = UUID("00000000-0000-0000-0000-000000000001")


@pytest.mark.asyncio
async def test_exams_intent_upsert_and_get(client, db_conn):
    from app.intents import courses as course_intent
    from app.intents import exams as intent
    from app.schemas import CourseCreate, ExamPatch

    await course_intent.create_course(OPERATOR, CourseCreate(code="EXMC", full_name="Exam Course"))
    exam = await intent.update_exam(OPERATOR, "EXMC", ExamPatch(scheduled_at="2026-07-15T10:00:00Z"))
    assert exam.course_code == "EXMC"

    fetched = await intent.get_exam(OPERATOR, "EXMC")
    assert fetched is not None
    assert fetched.course_code == "EXMC"


@pytest.mark.asyncio
async def test_exams_intent_list(client, db_conn):
    from app.intents import courses as course_intent
    from app.intents import exams as intent
    from app.schemas import CourseCreate, ExamPatch

    await course_intent.create_course(OPERATOR, CourseCreate(code="EXL", full_name="Exam List"))
    await intent.update_exam(OPERATOR, "EXL", ExamPatch())
    lst = await intent.list_exams(OPERATOR)
    assert any(e.course_code == "EXL" for e in lst)
