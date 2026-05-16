from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, Response, status

from ..auth import require_user, User
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
    user: User = Depends(require_user),
) -> List[Task]:
    return await intent.list_tasks(
        user.id,
        course_code=course_code,
        status=status,
        priority=priority,
        due_before=due_before,
        tag=tag,
    )


@router.post("", response_model=Task, status_code=status.HTTP_201_CREATED)
async def create(body: TaskCreate, user: User = Depends(require_user)) -> Task:
    return await intent.create_task(user.id, body)


@router.patch("/{task_id}", response_model=Task)
async def patch(task_id: str, body: TaskPatch, user: User = Depends(require_user)) -> Task:
    return await intent.update_task(user.id, task_id, body)


@router.post("/{task_id}/complete", response_model=Task)
async def complete(task_id: str, user: User = Depends(require_user)) -> Task:
    return await intent.complete_task(user.id, task_id)


@router.post("/{task_id}/reopen", response_model=Task)
async def reopen(task_id: str, user: User = Depends(require_user)) -> Task:
    return await intent.reopen_task(user.id, task_id)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete(task_id: str, user: User = Depends(require_user)) -> Response:
    await intent.delete_task(user.id, task_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
