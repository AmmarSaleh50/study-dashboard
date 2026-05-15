from typing import List
from fastapi import APIRouter, Depends, HTTPException, status

from ..auth import require_auth, SENTINEL_USER_ID
from ..schemas import Course, CourseCreate, CoursePatch
from ..intents import courses as intent

router = APIRouter(prefix="/courses", tags=["courses"])


@router.get("", response_model=List[Course])
async def list_(_: bool = Depends(require_auth)) -> List[Course]:
    return await intent.list_courses(SENTINEL_USER_ID)


@router.post("", response_model=Course, status_code=status.HTTP_201_CREATED)
async def create(body: CourseCreate, _: bool = Depends(require_auth)) -> Course:
    if await intent.get_course(SENTINEL_USER_ID, body.code) is not None:
        raise HTTPException(status_code=409, detail=f"course {body.code} already exists")
    return await intent.create_course(SENTINEL_USER_ID, body)


@router.get("/{code}", response_model=Course)
async def get(code: str, _: bool = Depends(require_auth)) -> Course:
    c = await intent.get_course(SENTINEL_USER_ID, code)
    if c is None:
        raise HTTPException(status_code=404, detail="course not found")
    return c


@router.patch("/{code}", response_model=Course)
async def patch(code: str, body: CoursePatch, _: bool = Depends(require_auth)) -> Course:
    return await intent.update_course(SENTINEL_USER_ID, code, body)


@router.delete("/{code}", status_code=status.HTTP_204_NO_CONTENT)
async def delete(code: str, _: bool = Depends(require_auth)) -> None:
    if await intent.get_course(SENTINEL_USER_ID, code) is None:
        raise HTTPException(status_code=404, detail="course not found")
    await intent.delete_course(SENTINEL_USER_ID, code)
