"""Course intents — single entry point for both REST and MCP callers."""
from typing import List
from uuid import UUID

from ..schemas import Course, CourseCreate, CoursePatch
from ..services import courses as svc


async def list_courses(user_id: UUID) -> List[Course]:
    return await svc.list_courses(user_id)


async def get_course(user_id: UUID, code: str) -> Course | None:
    return await svc.get_course(user_id, code)


async def create_course(user_id: UUID, body: CourseCreate) -> Course:
    return await svc.create_course(user_id, body)


async def update_course(user_id: UUID, code: str, patch: CoursePatch) -> Course:
    return await svc.update_course(user_id, code, patch)


async def delete_course(user_id: UUID, code: str) -> None:
    await svc.delete_course(user_id, code)
