"""Event intents — single entry point for both REST and MCP callers.

Today: thin pass-through to app.services.events. The user_id parameter
is accepted but ignored until Phase 2 wires up per-user filtering.
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
    return await svc.list_events(since, kind, course_code, limit)


async def record_event(user_id: UUID, payload: EventCreate) -> Event:
    return await svc.record_event(payload)
