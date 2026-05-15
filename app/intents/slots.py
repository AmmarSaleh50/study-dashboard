"""Schedule-slot intents — single entry point for both REST and MCP callers.

Today: thin pass-through to app.services.slots. The user_id parameter
is accepted but ignored until Phase 2 wires up per-user filtering.
"""
from typing import List, Optional
from uuid import UUID

from ..schemas import Slot, SlotCreate, SlotPatch
from ..services import slots as svc


async def list_slots(user_id: UUID, course_code: Optional[str] = None) -> List[Slot]:
    return await svc.list_slots(course_code)


async def create_slot(user_id: UUID, body: SlotCreate) -> Slot:
    return await svc.create_slot(body)


async def update_slot(user_id: UUID, slot_id: str, patch: SlotPatch) -> Slot:
    return await svc.update_slot(slot_id, patch)


async def delete_slot(user_id: UUID, slot_id: str) -> None:
    await svc.delete_slot(slot_id)
