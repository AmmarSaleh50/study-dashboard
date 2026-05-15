from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, Response, status

from ..auth import require_auth, SENTINEL_USER_ID
from ..schemas import Task, TaskCreate, TaskPatch
from ..intents import tasks as intent

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("", response_model=List[Task])
async def list_(
    course_code: Optional[str] = None,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    due_before: Optional[datetime] = None,
    tag: Optional[str] = None,
    _: bool = Depends(require_auth),
) -> List[Task]:
    return await intent.list_tasks(
        SENTINEL_USER_ID,
        course_code=course_code,
        status=status,
        priority=priority,
        due_before=due_before,
        tag=tag,
    )


@router.post("", response_model=Task, status_code=status.HTTP_201_CREATED)
async def create(body: TaskCreate, _: bool = Depends(require_auth)) -> Task:
    return await intent.create_task(SENTINEL_USER_ID, body)


@router.patch("/{task_id}", response_model=Task)
async def patch(task_id: str, body: TaskPatch, _: bool = Depends(require_auth)) -> Task:
    return await intent.update_task(SENTINEL_USER_ID, task_id, body)


@router.post("/{task_id}/complete", response_model=Task)
async def complete(task_id: str, _: bool = Depends(require_auth)) -> Task:
    return await intent.complete_task(SENTINEL_USER_ID, task_id)


@router.post("/{task_id}/reopen", response_model=Task)
async def reopen(task_id: str, _: bool = Depends(require_auth)) -> Task:
    return await intent.reopen_task(SENTINEL_USER_ID, task_id)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete(task_id: str, _: bool = Depends(require_auth)) -> Response:
    await intent.delete_task(SENTINEL_USER_ID, task_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
