import json
from datetime import datetime
from typing import List, Optional

from .. import db
from ..schemas import Event, EventCreate


async def list_events(
    since: Optional[datetime] = None,
    kind: Optional[str] = None,
    course_code: Optional[str] = None,
    limit: int = 100,
) -> List[Event]:
    where: list[str] = []
    args: list = []
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
    sql += " ORDER BY created_at DESC LIMIT %s"
    args.append(limit)
    rows = await db.fetch(sql, *args)
    return [Event.model_validate(r) for r in rows]


async def record_event(payload: EventCreate) -> Event:
    """Insert a row into `events`. JSONB payload is serialised via json.dumps
    + an explicit `::jsonb` cast so psycopg sends it as a single text param."""
    # `payload` here is the Pydantic model; its `.payload` attribute is the
    # event body dict (or None). Don't confuse with the variable name.
    payload_json = json.dumps(payload.payload) if payload.payload is not None else None
    row = await db.fetchrow(
        "INSERT INTO events (kind, course_code, payload) "
        "VALUES (%s, %s, %s::jsonb) RETURNING *",
        payload.kind, payload.course_code, payload_json,
    )
    if row is None:
        raise ValueError(f"failed to record event '{payload.kind}'")
    return Event.model_validate(row)


__all__ = ["list_events", "record_event"]
