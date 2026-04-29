from datetime import datetime, timezone
from typing import List, Optional

from .. import db
from ..schemas import Task, TaskCreate, TaskPatch
from ._helpers import model_dump_clean, validated_cols


async def list_tasks(
    course_code: Optional[str] = None,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    due_before: Optional[datetime] = None,
    tag: Optional[str] = None,
) -> List[Task]:
    where: list[str] = []
    args: list = []
    if course_code:
        where.append("course_code = %s")
        args.append(course_code)
    if status:
        where.append("status = %s")
        args.append(status)
    if priority:
        where.append("priority = %s")
        args.append(priority)
    if due_before:
        where.append("due_at <= %s")
        args.append(due_before)
    sql = "SELECT * FROM tasks"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY due_at"
    rows = await db.fetch(sql, *args)
    out = [Task.model_validate(r) for r in rows]
    if tag:
        out = [t for t in out if t.tags and tag in t.tags]
    return out


async def create_task(payload: TaskCreate) -> Task:
    data = model_dump_clean(payload)
    cols = validated_cols(TaskCreate, data)
    placeholders = ", ".join(["%s"] * len(cols))
    row = await db.fetchrow(
        f"INSERT INTO tasks ({', '.join(cols)}) "
        f"VALUES ({placeholders}) RETURNING *",
        *[data[c] for c in cols],
    )
    if row is None:
        raise ValueError(f"failed to create task '{payload.title}'")
    return Task.model_validate(row)


async def update_task(task_id: str, patch: TaskPatch) -> Task:
    data = model_dump_clean(patch)
    if not data:
        raise ValueError("empty patch")
    if data.get("status") == "done":
        data.setdefault("completed_at", datetime.now(timezone.utc).isoformat())
    elif data.get("status") in ("open", "in_progress", "blocked", "skipped"):
        # Clear completed_at when moving back out of done.
        data["completed_at"] = None
    # Validate against Task (the read model, superset of all DB columns) since
    # `completed_at` is injected here but isn't on TaskPatch.
    cols = validated_cols(Task, data)
    set_clause = ", ".join(f"{c} = %s" for c in cols)
    row = await db.fetchrow(
        f"UPDATE tasks SET {set_clause} WHERE id = %s RETURNING *",
        *[data[c] for c in cols], task_id,
    )
    if row is None:
        raise ValueError(f"task {task_id} not found")
    return Task.model_validate(row)


async def reopen_task(task_id: str) -> Task:
    return await update_task(task_id, TaskPatch(status="open"))


async def complete_task(task_id: str) -> Task:
    return await update_task(task_id, TaskPatch(status="done"))


async def delete_task(task_id: str) -> None:
    await db.execute("DELETE FROM tasks WHERE id = %s", task_id)


__all__ = [
    "list_tasks",
    "create_task",
    "update_task",
    "reopen_task",
    "complete_task",
    "delete_task",
]
