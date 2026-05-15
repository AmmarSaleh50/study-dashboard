from typing import List
from fastapi import APIRouter, Depends

from ..auth import require_auth, SENTINEL_USER_ID
from ..schemas import Exam, ExamPatch
from ..intents import exams as intent

router = APIRouter(prefix="/exams", tags=["exams"])


@router.get("", response_model=List[Exam])
async def list_(_: bool = Depends(require_auth)) -> List[Exam]:
    return await intent.list_exams(SENTINEL_USER_ID)


@router.patch("/{course_code}", response_model=Exam)
async def patch(
    course_code: str, body: ExamPatch, _: bool = Depends(require_auth)
) -> Exam:
    return await intent.update_exam(SENTINEL_USER_ID, course_code, body)
