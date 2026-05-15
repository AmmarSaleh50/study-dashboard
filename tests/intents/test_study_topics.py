"""Smoke test for app/intents/study_topics.py — proves the pass-through works.

Phase 2 will replace these with real per-user-scoping tests.
"""
import pytest
from uuid import UUID

OPERATOR = UUID("00000000-0000-0000-0000-000000000001")


@pytest.mark.asyncio
async def test_study_topics_intent_create_then_list(client, db_conn):
    from app.intents import courses as course_intent
    from app.intents import study_topics as intent
    from app.schemas import CourseCreate, StudyTopicCreate

    await course_intent.create_course(OPERATOR, CourseCreate(code="STPC", full_name="Topic Course"))
    topic = await intent.create_study_topic(
        OPERATOR,
        StudyTopicCreate(course_code="STPC", name="Chapter 1", kind="lecture"),
    )
    assert topic.course_code == "STPC"
    assert topic.name == "Chapter 1"

    lst = await intent.list_study_topics(OPERATOR, course_code="STPC")
    assert len(lst) == 1
    assert lst[0].name == "Chapter 1"
