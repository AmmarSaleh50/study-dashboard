from typing import List
from fastapi import APIRouter, Depends

from ..auth import require_user, User
from ..schemas import Exam, ExamPatch
from ..intents import exams as intent

router = APIRouter(prefix="/exams", tags=["exams"])


@router.get("", response_model=List[Exam])
async def list_(user: User = Depends(require_user)) -> List[Exam]:
    return await intent.list_exams(user.id)


@router.patch("/{course_code}", response_model=Exam)
async def patch(
    course_code: str, body: ExamPatch, user: User = Depends(require_user)
) -> Exam:
    return await intent.update_exam(user.id, course_code, body)
