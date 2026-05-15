"""Task intents — single entry point for both REST and MCP callers.

Today: thin pass-through to app.services.tasks. The user_id parameter
is accepted but ignored until Phase 2 wires up per-user filtering.
"""
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from ..schemas import Task, TaskCreate, TaskPatch
from ..services import tasks as svc


async def list_tasks(
    user_id: UUID,
    course_code: Optional[str] = None,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    due_before: Optional[datetime] = None,
    tag: Optional[str] = None,
) -> List[Task]:
    return await svc.list_tasks(course_code, status, priority, due_before, tag)


async def create_task(user_id: UUID, payload: TaskCreate) -> Task:
    return await svc.create_task(payload)


async def update_task(user_id: UUID, task_id: str, patch: TaskPatch) -> Task:
    return await svc.update_task(task_id, patch)


async def reopen_task(user_id: UUID, task_id: str) -> Task:
    return await svc.reopen_task(task_id)


async def complete_task(user_id: UUID, task_id: str) -> Task:
    return await svc.complete_task(task_id)


async def delete_task(user_id: UUID, task_id: str) -> None:
    await svc.delete_task(task_id)
