from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, Response, status

from ..auth import require_user, User
from ..schemas import Deliverable, DeliverableCreate, DeliverablePatch
from ..intents import deliverables as intent

router = APIRouter(prefix="/deliverables", tags=["deliverables"])


@router.get("", response_model=List[Deliverable])
async def list_(
    course_code: Optional[str] = None,
    status: Optional[str] = None,
    due_before: Optional[datetime] = None,
    user: User = Depends(require_user),
) -> List[Deliverable]:
    return await intent.list_deliverables(
        user.id, course_code=course_code, status=status, due_before=due_before
    )


@router.post("", response_model=Deliverable, status_code=status.HTTP_201_CREATED)
async def create(body: DeliverableCreate, user: User = Depends(require_user)) -> Deliverable:
    return await intent.create_deliverable(user.id, body)


@router.patch("/{deliverable_id}", response_model=Deliverable)
async def patch(
    deliverable_id: str, body: DeliverablePatch, user: User = Depends(require_user)
) -> Deliverable:
    return await intent.update_deliverable(user.id, deliverable_id, body)


@router.post("/{deliverable_id}/submit", response_model=Deliverable)
async def submit(deliverable_id: str, user: User = Depends(require_user)) -> Deliverable:
    return await intent.mark_submitted(user.id, deliverable_id)


@router.post("/{deliverable_id}/reopen", response_model=Deliverable)
async def reopen(deliverable_id: str, user: User = Depends(require_user)) -> Deliverable:
    return await intent.reopen_deliverable(user.id, deliverable_id)


@router.delete(
    "/{deliverable_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response
)
async def delete(deliverable_id: str, user: User = Depends(require_user)) -> Response:
    await intent.delete_deliverable(user.id, deliverable_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
