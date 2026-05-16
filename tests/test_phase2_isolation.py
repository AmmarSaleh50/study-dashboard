"""Phase 2 user-scoping invariants.

Proves the service-layer WHERE user_id = $1 filters genuinely isolate
data between users.

Each test:
- Inserts a second user into users.
- Has both the operator and the second user create some data of their own.
- Asserts each service's list_X(user_id) returns only that user's rows.
"""
from datetime import datetime, timezone, date
from uuid import UUID, uuid4

import pytest


OPERATOR = UUID("00000000-0000-0000-0000-000000000001")


async def _create_second_user(db_conn) -> UUID:
    """Insert a second user row directly and return its id."""
    second = uuid4()
    async with db_conn.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "INSERT INTO users (id, email, display_name) VALUES (%s, %s, %s)",
            (str(second), f"u-{second}@test", "Second"),
        )
    return second


@pytest.mark.asyncio
async def test_list_courses_only_returns_callers_data(client, db_conn):
    """Operator + second user each create a course; each sees only their own."""
    from app.services import courses as svc
    from app.schemas import CourseCreate

    second = await _create_second_user(db_conn)

    await svc.create_course(OPERATOR, CourseCreate(code="OPC", full_name="Op course"))
    await svc.create_course(second, CourseCreate(code="SUC", full_name="Sec course"))

    op_list = await svc.list_courses(OPERATOR)
    sec_list = await svc.list_courses(second)

    op_codes = {c.code for c in op_list}
    sec_codes = {c.code for c in sec_list}
    assert "OPC" in op_codes
    assert "OPC" not in sec_codes
    assert "SUC" in sec_codes
    assert "SUC" not in op_codes


@pytest.mark.asyncio
async def test_list_tasks_only_returns_callers_data(client, db_conn):
    """Operator + second user each create a task; each sees only their own."""
    from app.services import tasks as svc
    from app.schemas import TaskCreate

    second = await _create_second_user(db_conn)

    await svc.create_task(OPERATOR, TaskCreate(title="Op task"))
    await svc.create_task(second, TaskCreate(title="Sec task"))

    op_list = await svc.list_tasks(OPERATOR)
    sec_list = await svc.list_tasks(second)

    op_titles = {t.title for t in op_list}
    sec_titles = {t.title for t in sec_list}
    assert "Op task" in op_titles
    assert "Op task" not in sec_titles
    assert "Sec task" in sec_titles
    assert "Sec task" not in op_titles


@pytest.mark.asyncio
async def test_list_study_topics_only_returns_callers_data(client, db_conn):
    """Two users each create a course + topic; each sees only their own topic."""
    from app.services import courses as courses_svc, study_topics as topics_svc
    from app.schemas import CourseCreate, StudyTopicCreate

    second = await _create_second_user(db_conn)

    # Each user gets their own course (same code works thanks to composite PK).
    await courses_svc.create_course(OPERATOR, CourseCreate(code="ISO", full_name="Op iso"))
    await courses_svc.create_course(second, CourseCreate(code="ISO", full_name="Sec iso"))

    # Each user gets a topic in their ISO course.
    await topics_svc.create_study_topic(
        OPERATOR, StudyTopicCreate(course_code="ISO", name="Op topic", kind="lecture"),
    )
    await topics_svc.create_study_topic(
        second, StudyTopicCreate(course_code="ISO", name="Sec topic", kind="lecture"),
    )

    op_list = await topics_svc.list_study_topics(OPERATOR)
    sec_list = await topics_svc.list_study_topics(second)

    op_names = {t.name for t in op_list}
    sec_names = {t.name for t in sec_list}
    assert "Op topic" in op_names
    assert "Op topic" not in sec_names
    assert "Sec topic" in sec_names
    assert "Sec topic" not in op_names


@pytest.mark.asyncio
async def test_list_deliverables_only_returns_callers_data(client, db_conn):
    """Two users each create a course + deliverable; each sees only their own deliverable."""
    from app.services import courses as courses_svc, deliverables as deliv_svc
    from app.schemas import CourseCreate, DeliverableCreate

    second = await _create_second_user(db_conn)

    await courses_svc.create_course(OPERATOR, CourseCreate(code="DLC", full_name="Op del"))
    await courses_svc.create_course(second, CourseCreate(code="DLC", full_name="Sec del"))

    await deliv_svc.create_deliverable(OPERATOR, DeliverableCreate(
        course_code="DLC", name="Op del", kind="submission",
        due_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
    ))
    await deliv_svc.create_deliverable(second, DeliverableCreate(
        course_code="DLC", name="Sec del", kind="submission",
        due_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
    ))

    op_list = await deliv_svc.list_deliverables(OPERATOR)
    sec_list = await deliv_svc.list_deliverables(second)

    op_names = {d.name for d in op_list}
    sec_names = {d.name for d in sec_list}
    assert "Op del" in op_names
    assert "Op del" not in sec_names
    assert "Sec del" in sec_names
    assert "Sec del" not in op_names
