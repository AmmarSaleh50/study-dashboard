"""Event intents — single entry point for both REST and MCP callers.

Pass-through to app.services.events. The user_id parameter is forwarded to
the service, which filters by it via WHERE user_id = $1.
"""
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from ..schemas import Event, EventCreate
from ..services import events as svc


async def list_events(
    user_id: UUID,
    since: Optional[datetime] = None,
    kind: Optional[str] = None,
    course_code: Optional[str] = None,
    limit: int = 100,
) -> List[Event]:
    return await svc.list_events(user_id, since, kind, course_code, limit)


async def record_event(user_id: UUID, payload: EventCreate) -> Event:
    return await svc.record_event(user_id, payload)
