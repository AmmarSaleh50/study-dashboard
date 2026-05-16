from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends

from ..auth import require_user, User
from ..schemas import Event, EventCreate
from ..intents import events as intent

router = APIRouter(prefix="/events", tags=["events"])


@router.get("", response_model=List[Event])
async def list_(
    since: Optional[datetime] = None,
    kind: Optional[str] = None,
    course_code: Optional[str] = None,
    limit: int = 100,
    user: User = Depends(require_user),
) -> List[Event]:
    return await intent.list_events(user.id, since=since, kind=kind, course_code=course_code, limit=limit)


@router.post("", response_model=Event)
async def create(body: EventCreate, user: User = Depends(require_user)) -> Event:
    return await intent.record_event(user.id, body)
