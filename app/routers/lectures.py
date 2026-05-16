from typing import List, Optional
from fastapi import APIRouter, Depends, Response, status

from ..auth import require_user, User
from ..schemas import Lecture, LectureCreate, LecturePatch
from ..intents import lectures as intent

router = APIRouter(prefix="/lectures", tags=["lectures"])


@router.get("", response_model=List[Lecture])
async def list_(
    course_code: Optional[str] = None, user: User = Depends(require_user)
) -> List[Lecture]:
    return await intent.list_lectures(user.id, course_code=course_code)


@router.post("", response_model=Lecture, status_code=status.HTTP_201_CREATED)
async def create(body: LectureCreate, user: User = Depends(require_user)) -> Lecture:
    return await intent.create_lecture(user.id, body)


@router.patch("/{lecture_id}", response_model=Lecture)
async def patch(
    lecture_id: str, body: LecturePatch, user: User = Depends(require_user)
) -> Lecture:
    return await intent.update_lecture(user.id, lecture_id, body)


@router.post("/{lecture_id}/attended", response_model=Lecture)
async def attended(
    lecture_id: str, attended: bool = True, user: User = Depends(require_user)
) -> Lecture:
    return await intent.mark_attended(user.id, lecture_id, attended=attended)


@router.delete(
    "/{lecture_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response
)
async def delete(lecture_id: str, user: User = Depends(require_user)) -> Response:
    await intent.delete_lecture(user.id, lecture_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
