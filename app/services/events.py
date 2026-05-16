import json
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from .. import db
from ..schemas import Event, EventCreate


async def list_events(
    user_id: UUID,
    since: Optional[datetime] = None,
    kind: Optional[str] = None,
    course_code: Optional[str] = None,
    limit: int = 100,
) -> List[Event]:
    where: list[str] = ["user_id = %s"]
    args: list = [user_id]
    if since:
        where.append("created_at >= %s")
        args.append(since)
    if kind:
        where.append("kind = %s")
        args.append(kind)
    if course_code:
        where.append("course_code = %s")
        args.append(course_code)
    sql = "SELECT * FROM events"
    if where:
        sql += " WHERE " + " AND ".join(where)
    # Tie-break by `id` so events recorded inside the same transaction
    # (which share an identical `created_at = now()`) still get a stable
    # ordering — essential for batched activity-log displays.
    sql += " ORDER BY created_at DESC, id DESC LIMIT %s"
    args.append(limit)
    rows = await db.fetch(sql, *args)
    return [Event.model_validate(r) for r in rows]


async def record_event(user_id: UUID, payload: EventCreate) -> Event:
    """Insert a row into `events`. JSONB payload is serialised via json.dumps
    + an explicit `::jsonb` cast so psycopg sends it as a single text param.

    `created_at` is set to `clock_timestamp()` (microsecond-precision wall
    time) rather than the table-default `now()` (which is fixed for the
    entire transaction). Multiple events recorded inside one transaction
    therefore get distinct timestamps — important for activity-log
    ordering when batching, and required for correctness under per-test
    transaction-isolated test fixtures.
    """
    payload_json = json.dumps(payload.payload) if payload.payload is not None else None
    row = await db.fetchrow(
        "INSERT INTO events (user_id, kind, course_code, payload, created_at) "
        "VALUES (%s, %s, %s, %s::jsonb, clock_timestamp()) RETURNING *",
        user_id, payload.kind, payload.course_code, payload_json,
    )
    if row is None:
        raise ValueError(f"failed to record event '{payload.kind}'")
    return Event.model_validate(row)


__all__ = ["list_events", "record_event"]
