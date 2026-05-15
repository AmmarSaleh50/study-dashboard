"""Smoke test for app/intents/courses.py — proves the pass-through works.

Phase 2 will replace these with real per-user-scoping tests.
"""
import pytest
from uuid import UUID

OPERATOR = UUID("00000000-0000-0000-0000-000000000001")


@pytest.mark.asyncio
async def test_courses_intent_create_then_get(client, db_conn):
    from app.intents import courses as intent
    from app.schemas import CourseCreate

    created = await intent.create_course(OPERATOR, CourseCreate(code="ITEST", full_name="Intent test"))
    assert created.code == "ITEST"

    fetched = await intent.get_course(OPERATOR, "ITEST")
    assert fetched.code == "ITEST"


@pytest.mark.asyncio
async def test_courses_intent_list_and_delete(client, db_conn):
    from app.intents import courses as intent
    from app.schemas import CourseCreate

    await intent.create_course(OPERATOR, CourseCreate(code="IDEL", full_name="To delete"))
    lst = await intent.list_courses(OPERATOR)
    assert any(c.code == "IDEL" for c in lst)

    await intent.delete_course(OPERATOR, "IDEL")
    assert await intent.get_course(OPERATOR, "IDEL") is None
