"""Cascade-direction regression: deleting a course must cascade to every
table that references it. This locks behavior in before Phase 1
restructures the FK targets to composite (user_id, code).

Note: tasks.course_code is ON DELETE SET NULL (not CASCADE) — tasks are
'personal todos that may or may not belong to a course.' Other tables
CASCADE because they're course-specific by definition.
"""
from datetime import datetime, timezone, date

import pytest


@pytest.mark.asyncio
async def test_delete_course_cascades_to_children(client, db_conn):
    """Insert a course + one row per CASCADE child table, delete the course,
    confirm every child row is gone."""
    from app.schemas import (
        CourseCreate, TaskCreate, DeliverableCreate, LectureCreate,
        SlotCreate, StudyTopicCreate,
    )
    from app.services import (
        courses as courses_svc,
        tasks as tasks_svc,
        deliverables as deliverables_svc,
        lectures as lectures_svc,
        slots as slots_svc,
        study_topics as topics_svc,
    )

    code = "CASC1"

    # Seed the course + one row in each child table.
    await courses_svc.create_course(CourseCreate(code=code, full_name="Cascade test"))
    await tasks_svc.create_task(TaskCreate(course_code=code, title="task-row"))
    await deliverables_svc.create_deliverable(DeliverableCreate(
        course_code=code, name="del-row", kind="submission",
        due_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
    ))
    await lectures_svc.create_lecture(LectureCreate(
        course_code=code, held_on=date(2026, 5, 20), kind="lecture",
    ))
    await topics_svc.create_study_topic(StudyTopicCreate(
        course_code=code, name="topic-row", kind="lecture",
    ))
    await slots_svc.create_slot(SlotCreate(
        course_code=code, weekday=1, start_time="10:00", end_time="12:00",
        kind="lecture",
    ))

    # Sanity-check the children exist.
    async with db_conn.connection() as conn, conn.cursor() as cur:
        for table in ("tasks", "deliverables", "lectures", "study_topics", "schedule_slots"):
            await cur.execute(f"SELECT count(*) AS c FROM {table} WHERE course_code = %s", (code,))
            row = await cur.fetchone()
            assert row["c"] >= 1, f"{table} child row missing before delete"

    # Delete the course.
    await courses_svc.delete_course(code)

    # Tables that CASCADE: row must be gone.
    async with db_conn.connection() as conn, conn.cursor() as cur:
        for table in ("deliverables", "lectures", "study_topics", "schedule_slots"):
            await cur.execute(f"SELECT count(*) AS c FROM {table} WHERE course_code = %s", (code,))
            row = await cur.fetchone()
            assert row["c"] == 0, f"{table} did not CASCADE — {row['c']} row(s) left"


@pytest.mark.asyncio
async def test_delete_course_sets_null_on_tasks(client, db_conn):
    """tasks.course_code is ON DELETE SET NULL — the task row must survive
    with course_code = NULL, not be deleted."""
    from app.schemas import CourseCreate, TaskCreate
    from app.services import courses as courses_svc, tasks as tasks_svc

    code = "CASC2"
    await courses_svc.create_course(CourseCreate(code=code, full_name="SetNull test"))
    created = await tasks_svc.create_task(TaskCreate(course_code=code, title="orphaned-task"))

    await courses_svc.delete_course(code)

    # The task row still exists, with course_code now NULL.
    async with db_conn.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT id, course_code FROM tasks WHERE id = %s", (created.id,)
        )
        row = await cur.fetchone()
        assert row is not None, "task row was deleted (expected SET NULL)"
        assert row["course_code"] is None, f"task.course_code should be NULL, got {row['course_code']!r}"
