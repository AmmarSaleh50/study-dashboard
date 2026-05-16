"""Exam intents — single entry point for both REST and MCP callers."""
from typing import List
from uuid import UUID

from ..schemas import Exam, ExamPatch
from ..services import exams as svc


async def list_exams(user_id: UUID) -> List[Exam]:
    return await svc.list_exams(user_id)


async def get_exam(user_id: UUID, course_code: str) -> Exam | None:
    return await svc.get_exam(user_id, course_code)


async def update_exam(user_id: UUID, course_code: str, patch: ExamPatch) -> Exam:
    return await svc.update_exam(user_id, course_code, patch)
