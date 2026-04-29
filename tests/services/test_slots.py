"""Tests for app/services/slots.py."""
from datetime import time

import pytest


async def _seed_course(db_pool, code: str = "TEST") -> None:
    """Insert a courses row so slot FK constraint is satisfied."""
    async with db_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "INSERT INTO courses (code, full_name) VALUES (%s, %s) "
            "ON CONFLICT DO NOTHING",
            (code, f"Test course {code}"),
        )


@pytest.mark.asyncio
async def test_list_slots_empty(client, db_pool):
    from app.services import slots as svc
    result = await svc.list_slots()
    assert result == []


@pytest.mark.asyncio
async def test_create_then_list(client, db_pool):
    from app.schemas import SlotCreate
    from app.services import slots as svc
    await _seed_course(db_pool, "TEST")
    created = await svc.create_slot(SlotCreate(
        course_code="TEST",
        kind="lecture",
        weekday=1,
        start_time=time(10, 0),
        end_time=time(12, 0),
        room="A101",
    ))
    assert created.course_code == "TEST"
    assert created.kind == "lecture"
    assert created.weekday == 1
    assert created.start_time == time(10, 0)
    assert created.end_time == time(12, 0)
    assert created.room == "A101"
    assert created.id  # uuid string
    result = await svc.list_slots()
    assert len(result) == 1
    assert result[0].id == created.id


@pytest.mark.asyncio
async def test_list_slots_filtered_by_course(client, db_pool):
    from app.schemas import SlotCreate
    from app.services import slots as svc
    await _seed_course(db_pool, "AAA")
    await _seed_course(db_pool, "BBB")
    await svc.create_slot(SlotCreate(
        course_code="AAA", kind="lecture", weekday=1,
        start_time=time(8, 0), end_time=time(10, 0),
    ))
    await svc.create_slot(SlotCreate(
        course_code="BBB", kind="exercise", weekday=2,
        start_time=time(14, 0), end_time=time(16, 0),
    ))
    only_aaa = await svc.list_slots(course_code="AAA")
    assert len(only_aaa) == 1
    assert only_aaa[0].course_code == "AAA"
    only_bbb = await svc.list_slots(course_code="BBB")
    assert len(only_bbb) == 1
    assert only_bbb[0].course_code == "BBB"


@pytest.mark.asyncio
async def test_create_slot_missing_course_raises(client, db_pool):
    from app.schemas import SlotCreate
    from app.services import slots as svc
    # No course seeded — FK violation expected.
    with pytest.raises(Exception):
        await svc.create_slot(SlotCreate(
            course_code="NOPE", kind="lecture", weekday=1,
            start_time=time(10, 0), end_time=time(12, 0),
        ))


@pytest.mark.asyncio
async def test_update_slot(client, db_pool):
    from app.schemas import SlotCreate, SlotPatch
    from app.services import slots as svc
    await _seed_course(db_pool, "UPD")
    created = await svc.create_slot(SlotCreate(
        course_code="UPD", kind="lecture", weekday=1,
        start_time=time(9, 0), end_time=time(11, 0), room="A1",
    ))
    updated = await svc.update_slot(created.id, SlotPatch(room="B2", weekday=3))
    assert updated.room == "B2"
    assert updated.weekday == 3
    assert updated.kind == "lecture"  # unchanged
    assert updated.id == created.id


@pytest.mark.asyncio
async def test_update_slot_missing_id_raises(client, db_pool):
    from app.schemas import SlotPatch
    from app.services import slots as svc
    with pytest.raises(ValueError):
        await svc.update_slot(
            "00000000-0000-0000-0000-000000000000",
            SlotPatch(room="ghost"),
        )


@pytest.mark.asyncio
async def test_delete_slot(client, db_pool):
    from app.schemas import SlotCreate
    from app.services import slots as svc
    await _seed_course(db_pool, "DEL")
    created = await svc.create_slot(SlotCreate(
        course_code="DEL", kind="lecture", weekday=1,
        start_time=time(10, 0), end_time=time(12, 0),
    ))
    await svc.delete_slot(created.id)
    result = await svc.list_slots(course_code="DEL")
    assert result == []
