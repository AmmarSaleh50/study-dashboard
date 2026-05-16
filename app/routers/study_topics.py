from typing import List, Optional
from fastapi import APIRouter, Depends, Response, status

from ..auth import require_user, User
from ..schemas import LectureTopicsAdd, StudyTopic, StudyTopicCreate, StudyTopicPatch
from ..intents import study_topics as intent

router = APIRouter(prefix="/study-topics", tags=["study-topics"])


@router.get("", response_model=List[StudyTopic])
async def list_(
    course_code: Optional[str] = None,
    status: Optional[str] = None,
    user: User = Depends(require_user),
) -> List[StudyTopic]:
    return await intent.list_study_topics(user.id, course_code=course_code, status=status)


@router.post("", response_model=StudyTopic, status_code=status.HTTP_201_CREATED)
async def create(body: StudyTopicCreate, user: User = Depends(require_user)) -> StudyTopic:
    return await intent.create_study_topic(user.id, body)


@router.patch("/{topic_id}", response_model=StudyTopic)
async def patch(
    topic_id: str, body: StudyTopicPatch, user: User = Depends(require_user)
) -> StudyTopic:
    return await intent.update_study_topic(user.id, topic_id, body)


@router.post("/{topic_id}/studied", response_model=StudyTopic)
async def mark_studied(topic_id: str, user: User = Depends(require_user)) -> StudyTopic:
    return await intent.update_study_topic(user.id, topic_id, StudyTopicPatch(status="studied"))


@router.delete(
    "/{topic_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response
)
async def delete(topic_id: str, user: User = Depends(require_user)) -> Response:
    await intent.delete_study_topic(user.id, topic_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/bulk-from-lecture", response_model=List[StudyTopic])
async def bulk_from_lecture(
    body: LectureTopicsAdd, user: User = Depends(require_user)
) -> List[StudyTopic]:
    return await intent.add_lecture_topics(user.id, body)
