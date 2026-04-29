from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, Response, status

from ..auth import require_auth
from ..schemas import Deliverable, DeliverableCreate, DeliverablePatch
from ..services import deliverables as svc

router = APIRouter(prefix="/deliverables", tags=["deliverables"])


@router.get("", response_model=List[Deliverable])
async def list_(
    course_code: Optional[str] = None,
    status: Optional[str] = None,
    due_before: Optional[datetime] = None,
    _: bool = Depends(require_auth),
) -> List[Deliverable]:
    return await svc.list_deliverables(
        course_code=course_code, status=status, due_before=due_before
    )


@router.post("", response_model=Deliverable, status_code=status.HTTP_201_CREATED)
async def create(body: DeliverableCreate, _: bool = Depends(require_auth)) -> Deliverable:
    return await svc.create_deliverable(body)


@router.patch("/{deliverable_id}", response_model=Deliverable)
async def patch(
    deliverable_id: str, body: DeliverablePatch, _: bool = Depends(require_auth)
) -> Deliverable:
    return await svc.update_deliverable(deliverable_id, body)


@router.post("/{deliverable_id}/submit", response_model=Deliverable)
async def submit(deliverable_id: str, _: bool = Depends(require_auth)) -> Deliverable:
    return await svc.mark_submitted(deliverable_id)


@router.post("/{deliverable_id}/reopen", response_model=Deliverable)
async def reopen(deliverable_id: str, _: bool = Depends(require_auth)) -> Deliverable:
    return await svc.reopen_deliverable(deliverable_id)


@router.delete(
    "/{deliverable_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response
)
async def delete(deliverable_id: str, _: bool = Depends(require_auth)) -> Response:
    await svc.delete_deliverable(deliverable_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
