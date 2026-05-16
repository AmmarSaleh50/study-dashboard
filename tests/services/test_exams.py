"""Tests for app/services/exams.py.

Exams have a per-course singleton shape: at most one exam row per course
(course_code is the primary key). update_exam is upsert-style: insert if
missing, update if present.
"""
from datetime import datetime, timezone

import pytest

from app.auth import SENTINEL_USER_ID


async def _seed_course(db_conn, code: str) -> None:
    """Insert a courses row so the exam FK constraint is satisfied."""
    async with db_conn.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "INSERT INTO courses (user_id, code, full_name) VALUES (%s, %s, %s) "
            "ON CONFLICT DO NOTHING",
            (SENTINEL_USER_ID, code, f"Test course {code}"),
        )


@pytest.mark.asyncio
async def test_list_exams_empty(client, db_conn):
    from app.services import exams as svc
    result = await svc.list_exams(SENTINEL_USER_ID)
    assert result == []


@pytest.mark.asyncio
async def test_get_exam_missing_returns_none(client, db_conn):
    from app.services import exams as svc
    result = await svc.get_exam(SENTINEL_USER_ID, "EXAMT0")
    assert result is None


@pytest.mark.asyncio
async def test_update_exam_inserts_when_missing(client, db_conn):
    from app.schemas import ExamPatch
    from app.services import exams as svc
    await _seed_course(db_conn, "EXAMT1")

    scheduled = datetime(2026, 7, 20, 9, 0, tzinfo=timezone.utc)
    created = await svc.update_exam(
        SENTINEL_USER_ID,
        "EXAMT1",
        ExamPatch(
            scheduled_at=scheduled,
            duration_min=120,
            location="Room 101",
            structure="2 essays",
            aids_allowed="none",
            status="planned",
            weight_pct=100,
            notes="midterm",
        ),
    )
    assert created.course_code == "EXAMT1"
    assert created.scheduled_at == scheduled
    assert created.duration_min == 120
    assert created.location == "Room 101"
    assert created.structure == "2 essays"
    assert created.aids_allowed == "none"
    assert created.status == "planned"
    assert created.weight_pct == 100
    assert created.notes == "midterm"

    # Round-trip via get_exam
    fetched = await svc.get_exam(SENTINEL_USER_ID, "EXAMT1")
    assert fetched is not None
    assert fetched.scheduled_at == scheduled
    assert fetched.location == "Room 101"


@pytest.mark.asyncio
async def test_update_exam_updates_when_present(client, db_conn):
    from app.schemas import ExamPatch
    from app.services import exams as svc
    await _seed_course(db_conn, "EXAMT2")

    # First call: insert
    await svc.update_exam(
        SENTINEL_USER_ID,
        "EXAMT2",
        ExamPatch(
            scheduled_at=datetime(2026, 7, 20, 9, 0, tzinfo=timezone.utc),
            duration_min=90,
            location="Hall A",
            status="planned",
        ),
    )

    # Second call: update only some fields — others should remain.
    updated = await svc.update_exam(
        SENTINEL_USER_ID,
        "EXAMT2",
        ExamPatch(location="Hall B", status="confirmed"),
    )
    assert updated.course_code == "EXAMT2"
    assert updated.location == "Hall B"
    assert updated.status == "confirmed"
    # Untouched fields persist.
    assert updated.duration_min == 90
    assert updated.scheduled_at == datetime(2026, 7, 20, 9, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_update_exam_empty_patch_when_present_is_noop(client, db_conn):
    from app.schemas import ExamPatch
    from app.services import exams as svc
    await _seed_course(db_conn, "EXAMT3")
    seeded = await svc.update_exam(
        SENTINEL_USER_ID,
        "EXAMT3",
        ExamPatch(location="Original", duration_min=45),
    )
    # Empty patch on an existing row should return the existing row unchanged.
    result = await svc.update_exam(SENTINEL_USER_ID, "EXAMT3", ExamPatch())
    assert result.course_code == "EXAMT3"
    assert result.location == seeded.location
    assert result.duration_min == seeded.duration_min


@pytest.mark.asyncio
async def test_update_exam_empty_patch_when_missing_creates_default(client, db_conn):
    """Empty patch on a missing course should still insert a default row
    (course_code only). This matches the legacy upsert behavior."""
    from app.schemas import ExamPatch
    from app.services import exams as svc
    await _seed_course(db_conn, "EXAMT4")
    result = await svc.update_exam(SENTINEL_USER_ID, "EXAMT4", ExamPatch())
    assert result.course_code == "EXAMT4"
    # Defaults from schema
    assert result.status == "planned"
    assert result.weight_pct == 100
    # And it must actually be in the DB
    fetched = await svc.get_exam(SENTINEL_USER_ID, "EXAMT4")
    assert fetched is not None
    assert fetched.course_code == "EXAMT4"


@pytest.mark.asyncio
async def test_list_exams_returns_inserted(client, db_conn):
    from app.schemas import ExamPatch
    from app.services import exams as svc
    await _seed_course(db_conn, "EXAMT5")
    await svc.update_exam(
        SENTINEL_USER_ID,
        "EXAMT5",
        ExamPatch(
            scheduled_at=datetime(2026, 8, 1, 10, 0, tzinfo=timezone.utc),
            location="Aula",
        ),
    )
    rows = await svc.list_exams(SENTINEL_USER_ID)
    codes = {e.course_code for e in rows}
    assert "EXAMT5" in codes


@pytest.mark.asyncio
async def test_update_exam_missing_course_raises(client, db_conn):
    """No matching course row → FK violation on insert."""
    from app.schemas import ExamPatch
    from app.services import exams as svc
    with pytest.raises(Exception):
        await svc.update_exam(
            SENTINEL_USER_ID,
            "EXNOFK",
            ExamPatch(location="ghost"),
        )
