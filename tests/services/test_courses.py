"""Tests for app/services/courses.py."""
import pytest

from app.auth import SENTINEL_USER_ID


@pytest.mark.asyncio
async def test_list_courses_empty(client, db_conn):
    from app.services import courses as svc
    result = await svc.list_courses(SENTINEL_USER_ID)
    assert result == []


@pytest.mark.asyncio
async def test_create_then_list(client, db_conn):
    from app.services import courses as svc
    from app.schemas import CourseCreate
    created = await svc.create_course(SENTINEL_USER_ID, CourseCreate(
        code="TEST101",
        full_name="Test Course",
        ects=5,
    ))
    assert created.code == "TEST101"
    assert created.full_name == "Test Course"
    result = await svc.list_courses(SENTINEL_USER_ID)
    assert len(result) == 1
    assert result[0].code == "TEST101"


@pytest.mark.asyncio
async def test_get_course_missing(client, db_conn):
    from app.services import courses as svc
    result = await svc.get_course(SENTINEL_USER_ID, "DOES_NOT_EXIST")
    assert result is None


@pytest.mark.asyncio
async def test_update_course(client, db_conn):
    from app.services import courses as svc
    from app.schemas import CourseCreate, CoursePatch
    await svc.create_course(SENTINEL_USER_ID, CourseCreate(code="UPD", full_name="Original", ects=3))
    updated = await svc.update_course(SENTINEL_USER_ID, "UPD", CoursePatch(full_name="Renamed"))
    assert updated.full_name == "Renamed"
    assert updated.code == "UPD"  # unchanged


@pytest.mark.asyncio
async def test_delete_course(client, db_conn):
    from app.services import courses as svc
    from app.schemas import CourseCreate
    await svc.create_course(SENTINEL_USER_ID, CourseCreate(code="DEL", full_name="Doomed", ects=1))
    await svc.delete_course(SENTINEL_USER_ID, "DEL")
    assert await svc.get_course(SENTINEL_USER_ID, "DEL") is None
