"""Study-topic intents — single entry point for both REST and MCP callers.

Today: thin pass-through to app.services.study_topics. The user_id parameter
is accepted but ignored until Phase 2 wires up per-user filtering.
"""
from typing import List, Optional
from uuid import UUID

from ..schemas import LectureTopicsAdd, StudyTopic, StudyTopicCreate, StudyTopicPatch
from ..services import study_topics as svc


async def list_study_topics(
    user_id: UUID,
    course_code: Optional[str] = None,
    status: Optional[str] = None,
) -> List[StudyTopic]:
    return await svc.list_study_topics(course_code, status)


async def create_study_topic(user_id: UUID, payload: StudyTopicCreate) -> StudyTopic:
    return await svc.create_study_topic(payload)


async def update_study_topic(
    user_id: UUID, topic_id: str, patch: StudyTopicPatch
) -> StudyTopic:
    return await svc.update_study_topic(topic_id, patch)


async def delete_study_topic(user_id: UUID, topic_id: str) -> None:
    await svc.delete_study_topic(topic_id)


async def add_lecture_topics(user_id: UUID, payload: LectureTopicsAdd) -> List[StudyTopic]:
    return await svc.add_lecture_topics(payload)
