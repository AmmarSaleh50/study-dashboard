from typing import List, Optional
from fastapi import APIRouter, Depends, Response, status

from ..auth import require_auth
from ..schemas import LectureTopicsAdd, StudyTopic, StudyTopicCreate, StudyTopicPatch
from ..services import study_topics as svc

router = APIRouter(prefix="/study-topics", tags=["study-topics"])


@router.get("", response_model=List[StudyTopic])
async def list_(
    course_code: Optional[str] = None,
    status: Optional[str] = None,
    _: bool = Depends(require_auth),
) -> List[StudyTopic]:
    return await svc.list_study_topics(course_code=course_code, status=status)


@router.post("", response_model=StudyTopic, status_code=status.HTTP_201_CREATED)
async def create(body: StudyTopicCreate, _: bool = Depends(require_auth)) -> StudyTopic:
    return await svc.create_study_topic(body)


@router.patch("/{topic_id}", response_model=StudyTopic)
async def patch(
    topic_id: str, body: StudyTopicPatch, _: bool = Depends(require_auth)
) -> StudyTopic:
    return await svc.update_study_topic(topic_id, body)


@router.post("/{topic_id}/studied", response_model=StudyTopic)
async def mark_studied(topic_id: str, _: bool = Depends(require_auth)) -> StudyTopic:
    return await svc.update_study_topic(topic_id, StudyTopicPatch(status="studied"))


@router.delete(
    "/{topic_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response
)
async def delete(topic_id: str, _: bool = Depends(require_auth)) -> Response:
    await svc.delete_study_topic(topic_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/bulk-from-lecture", response_model=List[StudyTopic])
async def bulk_from_lecture(
    body: LectureTopicsAdd, _: bool = Depends(require_auth)
) -> List[StudyTopic]:
    return await svc.add_lecture_topics(body)
