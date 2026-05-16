"""Tests for app/services/tasks.py.

Tasks are personal todos. They have a nullable FK to courses
(`course_code text NULL REFERENCES courses(code) ON DELETE SET NULL`),
so a task can exist without a course but, if a code is supplied, the
referenced course row must exist.
"""
from datetime import datetime, timezone

import pytest

from app.auth import SENTINEL_USER_ID


async def _seed_course(db_conn, code: str) -> None:
    """Insert a courses row so the task FK constraint is satisfied."""
    async with db_conn.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "INSERT INTO courses (user_id, code, full_name) VALUES (%s, %s, %s) "
            "ON CONFLICT DO NOTHING",
            (SENTINEL_USER_ID, code, f"Test course {code}"),
        )


@pytest.mark.asyncio
async def test_list_tasks_empty(client, db_conn):
    from app.services import tasks as svc
    result = await svc.list_tasks(SENTINEL_USER_ID)
    assert result == []


@pytest.mark.asyncio
async def test_create_task_without_course(client, db_conn):
    """course_code is nullable on tasks — a personal todo has no course."""
    from app.schemas import TaskCreate
    from app.services import tasks as svc
    created = await svc.create_task(SENTINEL_USER_ID, TaskCreate(
        title="Buy groceries",
        priority="low",
    ))
    assert created.title == "Buy groceries"
    assert created.course_code is None
    assert created.status == "open"
    assert created.priority == "low"
    assert created.id  # uuid string


@pytest.mark.asyncio
async def test_create_task_with_course(client, db_conn):
    from app.schemas import TaskCreate
    from app.services import tasks as svc
    await _seed_course(db_conn, "TASKA")
    created = await svc.create_task(SENTINEL_USER_ID, TaskCreate(
        course_code="TASKA",
        title="Read chapter 1",
        description="for next week",
        due_at=datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc),
        status="open",
        priority="high",
        tags=["reading", "urgent"],
    ))
    assert created.course_code == "TASKA"
    assert created.title == "Read chapter 1"
    assert created.description == "for next week"
    assert created.due_at == datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)
    assert created.priority == "high"
    assert created.tags == ["reading", "urgent"]


@pytest.mark.asyncio
async def test_create_task_missing_course_raises(client, db_conn):
    """If a course_code is given but no such course exists, FK fails."""
    from app.schemas import TaskCreate
    from app.services import tasks as svc
    with pytest.raises(Exception):
        await svc.create_task(SENTINEL_USER_ID, TaskCreate(
            course_code="NOFKT",
            title="ghost",
        ))


@pytest.mark.asyncio
async def test_list_tasks_filtered_by_course(client, db_conn):
    from app.schemas import TaskCreate
    from app.services import tasks as svc
    await _seed_course(db_conn, "TASKB")
    await _seed_course(db_conn, "TASKC")
    await svc.create_task(SENTINEL_USER_ID, TaskCreate(course_code="TASKB", title="b1"))
    await svc.create_task(SENTINEL_USER_ID, TaskCreate(course_code="TASKC", title="c1"))
    only_b = await svc.list_tasks(SENTINEL_USER_ID, course_code="TASKB")
    assert len(only_b) >= 1
    assert all(t.course_code == "TASKB" for t in only_b)
    only_c = await svc.list_tasks(SENTINEL_USER_ID, course_code="TASKC")
    assert len(only_c) >= 1
    assert all(t.course_code == "TASKC" for t in only_c)


@pytest.mark.asyncio
async def test_list_tasks_filtered_by_status(client, db_conn):
    from app.schemas import TaskCreate
    from app.services import tasks as svc
    await _seed_course(db_conn, "TASKD")
    await svc.create_task(SENTINEL_USER_ID, TaskCreate(
        course_code="TASKD", title="open-one", status="open",
    ))
    await svc.create_task(SENTINEL_USER_ID, TaskCreate(
        course_code="TASKD", title="ip-one", status="in_progress",
    ))
    in_progress = await svc.list_tasks(SENTINEL_USER_ID, course_code="TASKD", status="in_progress")
    assert len(in_progress) == 1
    assert in_progress[0].status == "in_progress"
    assert in_progress[0].title == "ip-one"


@pytest.mark.asyncio
async def test_list_tasks_filtered_by_priority(client, db_conn):
    from app.schemas import TaskCreate
    from app.services import tasks as svc
    await _seed_course(db_conn, "TASKE")
    await svc.create_task(SENTINEL_USER_ID, TaskCreate(
        course_code="TASKE", title="low-one", priority="low",
    ))
    await svc.create_task(SENTINEL_USER_ID, TaskCreate(
        course_code="TASKE", title="urgent-one", priority="urgent",
    ))
    urgent = await svc.list_tasks(SENTINEL_USER_ID, course_code="TASKE", priority="urgent")
    assert len(urgent) == 1
    assert urgent[0].priority == "urgent"
    assert urgent[0].title == "urgent-one"


@pytest.mark.asyncio
async def test_list_tasks_filtered_by_due_before(client, db_conn):
    from app.schemas import TaskCreate
    from app.services import tasks as svc
    await _seed_course(db_conn, "TASKF")
    await svc.create_task(SENTINEL_USER_ID, TaskCreate(
        course_code="TASKF", title="early",
        due_at=datetime(2026, 4, 15, tzinfo=timezone.utc),
    ))
    await svc.create_task(SENTINEL_USER_ID, TaskCreate(
        course_code="TASKF", title="late",
        due_at=datetime(2026, 6, 15, tzinfo=timezone.utc),
    ))
    cutoff = datetime(2026, 5, 1, tzinfo=timezone.utc)
    early = await svc.list_tasks(SENTINEL_USER_ID, course_code="TASKF", due_before=cutoff)
    assert len(early) == 1
    assert early[0].title == "early"


@pytest.mark.asyncio
async def test_list_tasks_filtered_by_tag(client, db_conn):
    """Tag filtering is post-fetch (Python-side), not SQL."""
    from app.schemas import TaskCreate
    from app.services import tasks as svc
    await _seed_course(db_conn, "TASKG")
    await svc.create_task(SENTINEL_USER_ID, TaskCreate(
        course_code="TASKG", title="tagged", tags=["reading", "math"],
    ))
    await svc.create_task(SENTINEL_USER_ID, TaskCreate(
        course_code="TASKG", title="untagged",
    ))
    await svc.create_task(SENTINEL_USER_ID, TaskCreate(
        course_code="TASKG", title="other-tag", tags=["physics"],
    ))
    reading = await svc.list_tasks(SENTINEL_USER_ID, course_code="TASKG", tag="reading")
    assert len(reading) == 1
    assert reading[0].title == "tagged"


@pytest.mark.asyncio
async def test_update_task_changes_fields(client, db_conn):
    from app.schemas import TaskCreate, TaskPatch
    from app.services import tasks as svc
    await _seed_course(db_conn, "TASKH")
    created = await svc.create_task(SENTINEL_USER_ID, TaskCreate(
        course_code="TASKH", title="Original", priority="low",
    ))
    updated = await svc.update_task(
        SENTINEL_USER_ID, created.id, TaskPatch(title="Renamed", priority="high"),
    )
    assert updated.id == created.id
    assert updated.title == "Renamed"
    assert updated.priority == "high"
    # Untouched fields persist
    assert updated.course_code == "TASKH"
    assert updated.status == "open"


@pytest.mark.asyncio
async def test_update_task_empty_patch_raises(client, db_conn):
    from app.schemas import TaskPatch
    from app.services import tasks as svc
    with pytest.raises(ValueError):
        await svc.update_task(
            SENTINEL_USER_ID, "00000000-0000-0000-0000-000000000000", TaskPatch(),
        )


@pytest.mark.asyncio
async def test_update_task_missing_id_raises(client, db_conn):
    from app.schemas import TaskPatch
    from app.services import tasks as svc
    with pytest.raises(ValueError):
        await svc.update_task(
            SENTINEL_USER_ID,
            "00000000-0000-0000-0000-000000000000",
            TaskPatch(title="ghost"),
        )


@pytest.mark.asyncio
async def test_complete_task_sets_status_and_completed_at(client, db_conn):
    from app.schemas import TaskCreate
    from app.services import tasks as svc
    await _seed_course(db_conn, "TASKI")
    created = await svc.create_task(SENTINEL_USER_ID, TaskCreate(
        course_code="TASKI", title="To complete",
    ))
    assert created.status == "open"
    assert created.completed_at is None
    completed = await svc.complete_task(SENTINEL_USER_ID, created.id)
    assert completed.id == created.id
    assert completed.status == "done"
    assert completed.completed_at is not None


@pytest.mark.asyncio
async def test_reopen_task_clears_completed_at(client, db_conn):
    """Moving a task out of `done` clears completed_at."""
    from app.schemas import TaskCreate
    from app.services import tasks as svc
    await _seed_course(db_conn, "TASKJ")
    created = await svc.create_task(SENTINEL_USER_ID, TaskCreate(
        course_code="TASKJ", title="To reopen",
    ))
    completed = await svc.complete_task(SENTINEL_USER_ID, created.id)
    assert completed.completed_at is not None
    reopened = await svc.reopen_task(SENTINEL_USER_ID, created.id)
    assert reopened.id == created.id
    assert reopened.status == "open"
    assert reopened.completed_at is None


@pytest.mark.asyncio
async def test_update_task_to_in_progress_clears_completed_at(client, db_conn):
    """Any non-done status mutation clears completed_at."""
    from app.schemas import TaskCreate, TaskPatch
    from app.services import tasks as svc
    await _seed_course(db_conn, "TASKK")
    created = await svc.create_task(SENTINEL_USER_ID, TaskCreate(
        course_code="TASKK", title="Flip-flop",
    ))
    await svc.complete_task(SENTINEL_USER_ID, created.id)
    moved = await svc.update_task(SENTINEL_USER_ID, created.id, TaskPatch(status="in_progress"))
    assert moved.status == "in_progress"
    assert moved.completed_at is None


@pytest.mark.asyncio
async def test_delete_task(client, db_conn):
    from app.schemas import TaskCreate
    from app.services import tasks as svc
    await _seed_course(db_conn, "TASKL")
    created = await svc.create_task(SENTINEL_USER_ID, TaskCreate(
        course_code="TASKL", title="Doomed",
    ))
    await svc.delete_task(SENTINEL_USER_ID, created.id)
    result = await svc.list_tasks(SENTINEL_USER_ID, course_code="TASKL")
    assert all(t.id != created.id for t in result)
