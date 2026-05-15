"""Course intents — single entry point for both REST and MCP callers.

Today: thin pass-through to app.services.courses. The user_id parameter
is accepted but ignored until Phase 2 wires up per-user filtering.
"""
from typing import List
from uuid import UUID

from ..schemas import Course, CourseCreate, CoursePatch
from ..services import courses as svc


async def list_courses(user_id: UUID) -> List[Course]:
    return await svc.list_courses()


async def get_course(user_id: UUID, code: str) -> Course | None:
    return await svc.get_course(code)


async def create_course(user_id: UUID, body: CourseCreate) -> Course:
    return await svc.create_course(body)


async def update_course(user_id: UUID, code: str, patch: CoursePatch) -> Course:
    return await svc.update_course(code, patch)


async def delete_course(user_id: UUID, code: str) -> None:
    await svc.delete_course(code)
