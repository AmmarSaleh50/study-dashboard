from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends

from ..auth import require_auth, SENTINEL_USER_ID
from ..schemas import Event, EventCreate
from ..intents import events as intent

router = APIRouter(prefix="/events", tags=["events"])


@router.get("", response_model=List[Event])
async def list_(
    since: Optional[datetime] = None,
    kind: Optional[str] = None,
    course_code: Optional[str] = None,
    limit: int = 100,
    _: bool = Depends(require_auth),
) -> List[Event]:
    return await intent.list_events(SENTINEL_USER_ID, since=since, kind=kind, course_code=course_code, limit=limit)


@router.post("", response_model=Event)
async def create(body: EventCreate, _: bool = Depends(require_auth)) -> Event:
    return await intent.record_event(SENTINEL_USER_ID, body)
