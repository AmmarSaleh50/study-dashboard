from typing import List, Optional
from fastapi import APIRouter, Depends, Response, status

from ..auth import require_auth, SENTINEL_USER_ID
from ..schemas import Slot, SlotCreate, SlotPatch
from ..intents import slots as intent

router = APIRouter(prefix="/schedule-slots", tags=["schedule-slots"])


@router.get("", response_model=List[Slot])
async def list_(
    course_code: Optional[str] = None, _: bool = Depends(require_auth)
) -> List[Slot]:
    return await intent.list_slots(SENTINEL_USER_ID, course_code=course_code)


@router.post("", response_model=Slot, status_code=status.HTTP_201_CREATED)
async def create(body: SlotCreate, _: bool = Depends(require_auth)) -> Slot:
    return await intent.create_slot(SENTINEL_USER_ID, body)


@router.patch("/{slot_id}", response_model=Slot)
async def patch(slot_id: str, body: SlotPatch, _: bool = Depends(require_auth)) -> Slot:
    return await intent.update_slot(SENTINEL_USER_ID, slot_id, body)


@router.delete("/{slot_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete(slot_id: str, _: bool = Depends(require_auth)) -> Response:
    await intent.delete_slot(SENTINEL_USER_ID, slot_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
