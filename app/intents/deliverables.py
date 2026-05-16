"""Deliverable intents — single entry point for both REST and MCP callers."""
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from ..schemas import Deliverable, DeliverableCreate, DeliverablePatch
from ..services import deliverables as svc


async def list_deliverables(
    user_id: UUID,
    course_code: Optional[str] = None,
    status: Optional[str] = None,
    due_before: Optional[datetime] = None,
) -> List[Deliverable]:
    return await svc.list_deliverables(user_id, course_code, status, due_before)


async def create_deliverable(user_id: UUID, payload: DeliverableCreate) -> Deliverable:
    return await svc.create_deliverable(user_id, payload)


async def update_deliverable(
    user_id: UUID, deliverable_id: str, patch: DeliverablePatch
) -> Deliverable:
    return await svc.update_deliverable(user_id, deliverable_id, patch)


async def mark_submitted(user_id: UUID, deliverable_id: str) -> Deliverable:
    return await svc.mark_submitted(user_id, deliverable_id)


async def reopen_deliverable(user_id: UUID, deliverable_id: str) -> Deliverable:
    return await svc.reopen_deliverable(user_id, deliverable_id)


async def delete_deliverable(user_id: UUID, deliverable_id: str) -> None:
    await svc.delete_deliverable(user_id, deliverable_id)
