"""Tests for app/services/courses.py.

These will FAIL until Task 2.2 migrates courses.py to the new pool-based
db module. They're marked xfail to stay green in the meantime.
"""
import pytest

pytestmark = pytest.mark.xfail(
    reason="courses.py still uses PostgREST; tests pass after Task 2.2",
    strict=True,
)


@pytest.mark.asyncio
async def test_list_courses_empty(db_pool):
    from app.services import courses as svc
    result = await svc.list_courses()
    assert result == []


@pytest.mark.asyncio
async def test_create_then_list(db_pool):
    from app.services import courses as svc
    from app.schemas import CourseCreate
    created = await svc.create_course(CourseCreate(
        code="TEST101",
        full_name="Test Course",
        ects=5,
    ))
    assert created.code == "TEST101"
    assert created.full_name == "Test Course"
    result = await svc.list_courses()
    assert len(result) == 1
    assert result[0].code == "TEST101"


@pytest.mark.asyncio
async def test_get_course_missing(db_pool):
    from app.services import courses as svc
    result = await svc.get_course("DOES_NOT_EXIST")
    assert result is None


@pytest.mark.asyncio
async def test_update_course(db_pool):
    from app.services import courses as svc
    from app.schemas import CourseCreate, CoursePatch
    await svc.create_course(CourseCreate(code="UPD", full_name="Original", ects=3))
    updated = await svc.update_course("UPD", CoursePatch(full_name="Renamed"))
    assert updated.full_name == "Renamed"
    assert updated.code == "UPD"  # unchanged


@pytest.mark.asyncio
async def test_delete_course(db_pool):
    from app.services import courses as svc
    from app.schemas import CourseCreate
    await svc.create_course(CourseCreate(code="DEL", full_name="Doomed", ects=1))
    await svc.delete_course("DEL")
    assert await svc.get_course("DEL") is None
