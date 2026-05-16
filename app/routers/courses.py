from typing import List
from fastapi import APIRouter, Depends, HTTPException, status

from ..auth import require_user, User
from ..schemas import Course, CourseCreate, CoursePatch
from ..intents import courses as intent

router = APIRouter(prefix="/courses", tags=["courses"])


@router.get("", response_model=List[Course])
async def list_(user: User = Depends(require_user)) -> List[Course]:
    return await intent.list_courses(user.id)


@router.post("", response_model=Course, status_code=status.HTTP_201_CREATED)
async def create(body: CourseCreate, user: User = Depends(require_user)) -> Course:
    if await intent.get_course(user.id, body.code) is not None:
        raise HTTPException(status_code=409, detail=f"course {body.code} already exists")
    return await intent.create_course(user.id, body)


@router.get("/{code}", response_model=Course)
async def get(code: str, user: User = Depends(require_user)) -> Course:
    c = await intent.get_course(user.id, code)
    if c is None:
        raise HTTPException(status_code=404, detail="course not found")
    return c


@router.patch("/{code}", response_model=Course)
async def patch(code: str, body: CoursePatch, user: User = Depends(require_user)) -> Course:
    return await intent.update_course(user.id, code, body)


@router.delete("/{code}", status_code=status.HTTP_204_NO_CONTENT)
async def delete(code: str, user: User = Depends(require_user)) -> None:
    if await intent.get_course(user.id, code) is None:
        raise HTTPException(status_code=404, detail="course not found")
    await intent.delete_course(user.id, code)
