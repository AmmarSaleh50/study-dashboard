"""Tests for app/services/deliverables.py."""
from datetime import datetime, timezone

import pytest

from app.auth import SENTINEL_USER_ID


async def _seed_course(db_conn, code: str = "TEST") -> None:
    """Insert a courses row so deliverable FK constraint is satisfied."""
    async with db_conn.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "INSERT INTO courses (code, full_name) VALUES (%s, %s) "
            "ON CONFLICT DO NOTHING",
            (code, f"Test course {code}"),
        )


@pytest.mark.asyncio
async def test_list_deliverables_empty(client, db_conn):
    from app.services import deliverables as svc
    result = await svc.list_deliverables(SENTINEL_USER_ID)
    assert result == []


@pytest.mark.asyncio
async def test_create_then_list(client, db_conn):
    from app.schemas import DeliverableCreate
    from app.services import deliverables as svc
    await _seed_course(db_conn, "DEL1")
    created = await svc.create_deliverable(SENTINEL_USER_ID, DeliverableCreate(
        course_code="DEL1",
        kind="submission",
        name="Problem set 1",
        due_at=datetime(2026, 5, 1, 23, 59, tzinfo=timezone.utc),
        status="open",
        notes="initial",
    ))
    assert created.course_code == "DEL1"
    assert created.name == "Problem set 1"
    assert created.kind == "submission"
    assert created.status == "open"
    assert created.due_at == datetime(2026, 5, 1, 23, 59, tzinfo=timezone.utc)
    assert created.id  # uuid string

    result = await svc.list_deliverables(SENTINEL_USER_ID)
    assert len(result) == 1
    assert result[0].id == created.id


@pytest.mark.asyncio
async def test_list_deliverables_filtered_by_course(client, db_conn):
    from app.schemas import DeliverableCreate
    from app.services import deliverables as svc
    await _seed_course(db_conn, "AAA")
    await _seed_course(db_conn, "BBB")
    await svc.create_deliverable(SENTINEL_USER_ID, DeliverableCreate(
        course_code="AAA", name="A-set",
        due_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
    ))
    await svc.create_deliverable(SENTINEL_USER_ID, DeliverableCreate(
        course_code="BBB", name="B-set",
        due_at=datetime(2026, 5, 2, tzinfo=timezone.utc),
    ))
    only_aaa = await svc.list_deliverables(SENTINEL_USER_ID, course_code="AAA")
    assert len(only_aaa) == 1
    assert only_aaa[0].course_code == "AAA"
    only_bbb = await svc.list_deliverables(SENTINEL_USER_ID, course_code="BBB")
    assert len(only_bbb) == 1
    assert only_bbb[0].course_code == "BBB"


@pytest.mark.asyncio
async def test_list_deliverables_filtered_by_status(client, db_conn):
    from app.schemas import DeliverableCreate
    from app.services import deliverables as svc
    await _seed_course(db_conn, "STA")
    await svc.create_deliverable(SENTINEL_USER_ID, DeliverableCreate(
        course_code="STA", name="open-one", status="open",
        due_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
    ))
    await svc.create_deliverable(SENTINEL_USER_ID, DeliverableCreate(
        course_code="STA", name="submitted-one", status="submitted",
        due_at=datetime(2026, 5, 2, tzinfo=timezone.utc),
    ))
    submitted_only = await svc.list_deliverables(SENTINEL_USER_ID, status="submitted")
    assert len(submitted_only) == 1
    assert submitted_only[0].status == "submitted"
    assert submitted_only[0].name == "submitted-one"


@pytest.mark.asyncio
async def test_list_deliverables_filtered_by_due_before(client, db_conn):
    from app.schemas import DeliverableCreate
    from app.services import deliverables as svc
    await _seed_course(db_conn, "DUE")
    await svc.create_deliverable(SENTINEL_USER_ID, DeliverableCreate(
        course_code="DUE", name="early",
        due_at=datetime(2026, 4, 15, tzinfo=timezone.utc),
    ))
    await svc.create_deliverable(SENTINEL_USER_ID, DeliverableCreate(
        course_code="DUE", name="late",
        due_at=datetime(2026, 6, 15, tzinfo=timezone.utc),
    ))
    cutoff = datetime(2026, 5, 1, tzinfo=timezone.utc)
    early_only = await svc.list_deliverables(SENTINEL_USER_ID, course_code="DUE", due_before=cutoff)
    assert len(early_only) == 1
    assert early_only[0].name == "early"


@pytest.mark.asyncio
async def test_create_deliverable_missing_course_raises(client, db_conn):
    from app.schemas import DeliverableCreate
    from app.services import deliverables as svc
    # No course seeded — FK violation expected.
    with pytest.raises(Exception):
        await svc.create_deliverable(SENTINEL_USER_ID, DeliverableCreate(
            course_code="NOPE", name="ghost",
            due_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        ))


@pytest.mark.asyncio
async def test_update_deliverable(client, db_conn):
    from app.schemas import DeliverableCreate, DeliverablePatch
    from app.services import deliverables as svc
    await _seed_course(db_conn, "UPD")
    created = await svc.create_deliverable(SENTINEL_USER_ID, DeliverableCreate(
        course_code="UPD", name="Original",
        due_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        status="open",
    ))
    updated = await svc.update_deliverable(
        SENTINEL_USER_ID, created.id, DeliverablePatch(name="Renamed", notes="updated"),
    )
    assert updated.name == "Renamed"
    assert updated.notes == "updated"
    assert updated.status == "open"  # unchanged
    assert updated.id == created.id


@pytest.mark.asyncio
async def test_update_deliverable_empty_patch_raises(client, db_conn):
    from app.schemas import DeliverablePatch
    from app.services import deliverables as svc
    with pytest.raises(ValueError):
        await svc.update_deliverable(
            SENTINEL_USER_ID,
            "00000000-0000-0000-0000-000000000000",
            DeliverablePatch(),
        )


@pytest.mark.asyncio
async def test_update_deliverable_missing_id_raises(client, db_conn):
    from app.schemas import DeliverablePatch
    from app.services import deliverables as svc
    with pytest.raises(ValueError):
        await svc.update_deliverable(
            SENTINEL_USER_ID,
            "00000000-0000-0000-0000-000000000000",
            DeliverablePatch(name="ghost"),
        )


@pytest.mark.asyncio
async def test_mark_submitted_flips_status(client, db_conn):
    from app.schemas import DeliverableCreate
    from app.services import deliverables as svc
    await _seed_course(db_conn, "SUB")
    created = await svc.create_deliverable(SENTINEL_USER_ID, DeliverableCreate(
        course_code="SUB", name="To submit",
        due_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        status="open",
    ))
    assert created.status == "open"
    submitted = await svc.mark_submitted(SENTINEL_USER_ID, created.id)
    assert submitted.status == "submitted"
    assert submitted.id == created.id


@pytest.mark.asyncio
async def test_mark_submitted_idempotent(client, db_conn):
    from app.schemas import DeliverableCreate
    from app.services import deliverables as svc
    await _seed_course(db_conn, "IDM")
    created = await svc.create_deliverable(SENTINEL_USER_ID, DeliverableCreate(
        course_code="IDM", name="Idempotent",
        due_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        status="open",
    ))
    first = await svc.mark_submitted(SENTINEL_USER_ID, created.id)
    assert first.status == "submitted"
    # Marking submitted again should not error and should remain submitted.
    second = await svc.mark_submitted(SENTINEL_USER_ID, created.id)
    assert second.status == "submitted"
    assert second.id == created.id


@pytest.mark.asyncio
async def test_reopen_deliverable_flips_status(client, db_conn):
    from app.schemas import DeliverableCreate
    from app.services import deliverables as svc
    await _seed_course(db_conn, "REO")
    created = await svc.create_deliverable(SENTINEL_USER_ID, DeliverableCreate(
        course_code="REO", name="To reopen",
        due_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        status="submitted",
    ))
    assert created.status == "submitted"
    reopened = await svc.reopen_deliverable(SENTINEL_USER_ID, created.id)
    assert reopened.status == "open"
    assert reopened.id == created.id


@pytest.mark.asyncio
async def test_delete_deliverable(client, db_conn):
    from app.schemas import DeliverableCreate
    from app.services import deliverables as svc
    await _seed_course(db_conn, "DELE")
    created = await svc.create_deliverable(SENTINEL_USER_ID, DeliverableCreate(
        course_code="DELE", name="Doomed",
        due_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
    ))
    await svc.delete_deliverable(SENTINEL_USER_ID, created.id)
    result = await svc.list_deliverables(SENTINEL_USER_ID, course_code="DELE")
    assert result == []
