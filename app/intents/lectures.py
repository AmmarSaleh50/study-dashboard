"""Lecture intents — single entry point for both REST and MCP callers.

Today: thin pass-through to app.services.lectures. The user_id parameter
is accepted but ignored until Phase 2 wires up per-user filtering.
"""
from typing import List, Optional
from uuid import UUID

from ..schemas import Lecture, LectureCreate, LecturePatch
from ..services import lectures as svc


async def list_lectures(user_id: UUID, course_code: Optional[str] = None) -> List[Lecture]:
    return await svc.list_lectures(course_code)


async def get_lecture(user_id: UUID, lecture_id: str) -> Optional[Lecture]:
    return await svc.get_lecture(lecture_id)


async def create_lecture(user_id: UUID, payload: LectureCreate) -> Lecture:
    return await svc.create_lecture(payload)


async def update_lecture(user_id: UUID, lecture_id: str, patch: LecturePatch) -> Lecture:
    return await svc.update_lecture(lecture_id, patch)


async def mark_attended(user_id: UUID, lecture_id: str, attended: bool = True) -> Lecture:
    return await svc.mark_attended(lecture_id, attended)


async def delete_lecture(user_id: UUID, lecture_id: str) -> None:
    await svc.delete_lecture(lecture_id)
