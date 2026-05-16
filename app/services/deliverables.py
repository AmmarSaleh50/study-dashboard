from datetime import datetime
from typing import List, Optional
from uuid import UUID

from .. import db
from ..schemas import Deliverable, DeliverableCreate, DeliverablePatch
from ._helpers import model_dump_clean, validated_cols


async def list_deliverables(
    user_id: UUID,
    course_code: Optional[str] = None,
    status: Optional[str] = None,
    due_before: Optional[datetime] = None,
) -> List[Deliverable]:
    where: list[str] = ["user_id = %s"]
    args: list = [user_id]
    if course_code:
        where.append("course_code = %s")
        args.append(course_code)
    if status:
        where.append("status = %s")
        args.append(status)
    if due_before:
        where.append("due_at <= %s")
        args.append(due_before)
    sql = "SELECT * FROM deliverables WHERE " + " AND ".join(where)
    sql += " ORDER BY due_at"
    rows = await db.fetch(sql, *args)
    return [Deliverable.model_validate(r) for r in rows]


async def create_deliverable(user_id: UUID, payload: DeliverableCreate) -> Deliverable:
    data = model_dump_clean(payload)
    cols = validated_cols(DeliverableCreate, data)
    placeholders = ", ".join(["%s"] * (len(cols) + 1))
    row = await db.fetchrow(
        f"INSERT INTO deliverables (user_id, {', '.join(cols)}) "
        f"VALUES ({placeholders}) RETURNING *",
        user_id, *[data[c] for c in cols],
    )
    if row is None:
        raise ValueError(f"failed to create deliverable for {payload.course_code}")
    return Deliverable.model_validate(row)


async def update_deliverable(user_id: UUID, deliverable_id: str, patch: DeliverablePatch) -> Deliverable:
    data = model_dump_clean(patch)
    if not data:
        raise ValueError("empty patch")
    cols = validated_cols(DeliverablePatch, data)
    set_clause = ", ".join(f"{c} = %s" for c in cols)
    row = await db.fetchrow(
        f"UPDATE deliverables SET {set_clause} WHERE id = %s AND user_id = %s RETURNING *",
        *[data[c] for c in cols], deliverable_id, user_id,
    )
    if row is None:
        raise ValueError(f"deliverable {deliverable_id} not found")
    return Deliverable.model_validate(row)


async def mark_submitted(user_id: UUID, deliverable_id: str) -> Deliverable:
    return await update_deliverable(
        user_id, deliverable_id, DeliverablePatch(status="submitted")
    )


async def reopen_deliverable(user_id: UUID, deliverable_id: str) -> Deliverable:
    return await update_deliverable(
        user_id, deliverable_id, DeliverablePatch(status="open")
    )


async def delete_deliverable(user_id: UUID, deliverable_id: str) -> None:
    await db.execute("DELETE FROM deliverables WHERE id = %s AND user_id = %s", deliverable_id, user_id)


__all__ = [
    "list_deliverables",
    "create_deliverable",
    "update_deliverable",
    "mark_submitted",
    "reopen_deliverable",
    "delete_deliverable",
]
