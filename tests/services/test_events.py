"""Tests for app/services/events.py.

Events are the activity log: insert-only, ordered by created_at desc.
The schema has no FK requirement on `kind`, but `course_code` is a soft
FK (`ON DELETE SET NULL`) — so a referenced course must exist if supplied.

Note: the baseline schema has triggers (`trg_log_change_*`) that
auto-insert events on every mutation of `courses`, `tasks`, etc. These
tests use unique `kind` labels (prefixed `evt:test:*`) and filter by
kind so the trigger-generated rows from other tests don't pollute results.
"""
from datetime import datetime, timedelta, timezone

import pytest


async def _seed_course(db_pool, code: str) -> None:
    """Insert a courses row so the events FK constraint is satisfied."""
    async with db_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "INSERT INTO courses (code, full_name) VALUES (%s, %s) "
            "ON CONFLICT DO NOTHING",
            (code, f"Test course {code}"),
        )


@pytest.mark.asyncio
async def test_list_events_filtered_by_unknown_kind_is_empty(client, db_pool):
    """Unknown kind label → empty list (proves filter actually filters)."""
    from app.services import events as svc
    result = await svc.list_events(kind="evt:test:does_not_exist")
    assert result == []


@pytest.mark.asyncio
async def test_record_event_minimal(client, db_pool):
    """Bare-minimum event: kind only, no payload, no course."""
    from app.schemas import EventCreate
    from app.services import events as svc
    created = await svc.record_event(EventCreate(kind="evt:test:minimal"))
    assert created.kind == "evt:test:minimal"
    assert created.course_code is None
    assert created.payload is None
    assert created.id  # uuid string
    assert created.created_at is not None


@pytest.mark.asyncio
async def test_record_event_with_payload_and_course(client, db_pool):
    """Full event: payload (jsonb) + course_code FK."""
    from app.schemas import EventCreate
    from app.services import events as svc
    await _seed_course(db_pool, "EVTA")
    payload = {"action": "studied", "duration_min": 45, "topics": ["a", "b"]}
    created = await svc.record_event(EventCreate(
        kind="evt:test:full",
        course_code="EVTA",
        payload=payload,
    ))
    assert created.kind == "evt:test:full"
    assert created.course_code == "EVTA"
    # JSONB round-trips as a Python dict (psycopg auto-deserializes).
    assert created.payload == payload


@pytest.mark.asyncio
async def test_record_then_list_by_kind(client, db_pool):
    """Inserted events are retrievable via list_events filtered by kind."""
    from app.schemas import EventCreate
    from app.services import events as svc
    await svc.record_event(EventCreate(
        kind="evt:test:list_kind",
        payload={"n": 1},
    ))
    await svc.record_event(EventCreate(
        kind="evt:test:list_kind",
        payload={"n": 2},
    ))
    result = await svc.list_events(kind="evt:test:list_kind")
    assert len(result) == 2
    assert all(e.kind == "evt:test:list_kind" for e in result)


@pytest.mark.asyncio
async def test_list_events_filtered_by_course_code(client, db_pool):
    """Filtering by course_code returns only events for that course."""
    from app.schemas import EventCreate
    from app.services import events as svc
    await _seed_course(db_pool, "EVTB")
    await _seed_course(db_pool, "EVTC")
    await svc.record_event(EventCreate(
        kind="evt:test:by_course",
        course_code="EVTB",
        payload={"n": 1},
    ))
    await svc.record_event(EventCreate(
        kind="evt:test:by_course",
        course_code="EVTC",
        payload={"n": 2},
    ))
    only_b = await svc.list_events(kind="evt:test:by_course", course_code="EVTB")
    assert len(only_b) == 1
    assert only_b[0].course_code == "EVTB"
    assert only_b[0].payload == {"n": 1}
    only_c = await svc.list_events(kind="evt:test:by_course", course_code="EVTC")
    assert len(only_c) == 1
    assert only_c[0].course_code == "EVTC"


@pytest.mark.asyncio
async def test_list_events_filtered_by_since(client, db_pool):
    """`since` filters out events created before the cutoff."""
    from app.schemas import EventCreate
    from app.services import events as svc
    await svc.record_event(EventCreate(kind="evt:test:since_old"))
    cutoff = datetime.now(timezone.utc) + timedelta(seconds=1)
    # Sleep is overkill here; just use a future cutoff to confirm filter works.
    result = await svc.list_events(
        kind="evt:test:since_old",
        since=cutoff,
    )
    assert result == []  # cutoff is after the recorded event


@pytest.mark.asyncio
async def test_list_events_orders_newest_first(client, db_pool):
    """list_events orders by created_at DESC (newest first)."""
    from app.schemas import EventCreate
    from app.services import events as svc
    first = await svc.record_event(EventCreate(
        kind="evt:test:order", payload={"n": 1},
    ))
    second = await svc.record_event(EventCreate(
        kind="evt:test:order", payload={"n": 2},
    ))
    result = await svc.list_events(kind="evt:test:order")
    assert len(result) == 2
    # Newest first: second should come before first.
    assert result[0].id == second.id
    assert result[1].id == first.id


@pytest.mark.asyncio
async def test_list_events_respects_limit(client, db_pool):
    """`limit` caps the number of returned rows."""
    from app.schemas import EventCreate
    from app.services import events as svc
    for i in range(5):
        await svc.record_event(EventCreate(
            kind="evt:test:limit", payload={"n": i},
        ))
    result = await svc.list_events(kind="evt:test:limit", limit=2)
    assert len(result) == 2


@pytest.mark.asyncio
async def test_record_event_missing_course_raises(client, db_pool):
    """If course_code is given but no such course exists, FK fails."""
    from app.schemas import EventCreate
    from app.services import events as svc
    with pytest.raises(Exception):
        await svc.record_event(EventCreate(
            kind="evt:test:fk_fail",
            course_code="NOFKE",
        ))
