from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends

from ..auth import require_auth
from ..schemas import Event, EventCreate
from ..services import events as svc

router = APIRouter(prefix="/events", tags=["events"])


@router.get("", response_model=List[Event])
async def list_(
    since: Optional[datetime] = None,
    kind: Optional[str] = None,
    course_code: Optional[str] = None,
    limit: int = 100,
    _: bool = Depends(require_auth),
) -> List[Event]:
    return await svc.list_events(since=since, kind=kind, course_code=course_code, limit=limit)


@router.post("", response_model=Event)
async def create(body: EventCreate, _: bool = Depends(require_auth)) -> Event:
    return await svc.record_event(body)
