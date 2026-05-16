"""Tests for app/services/study_topics.py."""
from datetime import date

import pytest

from app.auth import SENTINEL_USER_ID


async def _seed_course(db_conn, code: str = "TEST") -> None:
    """Insert a courses row so study_topics FK constraint is satisfied."""
    async with db_conn.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "INSERT INTO courses (user_id, code, full_name) VALUES (%s, %s, %s) "
            "ON CONFLICT DO NOTHING",
            (SENTINEL_USER_ID, code, f"Test course {code}"),
        )


@pytest.mark.asyncio
async def test_list_study_topics_empty(client, db_conn):
    from app.services import study_topics as svc
    result = await svc.list_study_topics(SENTINEL_USER_ID)
    assert result == []


@pytest.mark.asyncio
async def test_create_then_list(client, db_conn):
    from app.schemas import StudyTopicCreate
    from app.services import study_topics as svc
    await _seed_course(db_conn, "ST1")
    created = await svc.create_study_topic(SENTINEL_USER_ID, StudyTopicCreate(
        course_code="ST1",
        chapter="1",
        name="Intro",
        description="Overview",
        kind="lecture",
        covered_on=date(2026, 4, 1),
        status="not_started",
        confidence=2,
        sort_order=0,
    ))
    assert created.course_code == "ST1"
    assert created.name == "Intro"
    assert created.kind == "lecture"
    assert created.status == "not_started"
    assert created.confidence == 2
    assert created.sort_order == 0
    assert created.id  # uuid string

    result = await svc.list_study_topics(SENTINEL_USER_ID)
    assert len(result) == 1
    assert result[0].id == created.id


@pytest.mark.asyncio
async def test_list_study_topics_filtered_by_course(client, db_conn):
    from app.schemas import StudyTopicCreate
    from app.services import study_topics as svc
    await _seed_course(db_conn, "AAA")
    await _seed_course(db_conn, "BBB")
    await svc.create_study_topic(SENTINEL_USER_ID, StudyTopicCreate(
        course_code="AAA", name="A-topic",
    ))
    await svc.create_study_topic(SENTINEL_USER_ID, StudyTopicCreate(
        course_code="BBB", name="B-topic",
    ))
    only_aaa = await svc.list_study_topics(SENTINEL_USER_ID, course_code="AAA")
    assert len(only_aaa) == 1
    assert only_aaa[0].course_code == "AAA"
    only_bbb = await svc.list_study_topics(SENTINEL_USER_ID, course_code="BBB")
    assert len(only_bbb) == 1
    assert only_bbb[0].course_code == "BBB"


@pytest.mark.asyncio
async def test_list_study_topics_filtered_by_status(client, db_conn):
    from app.schemas import StudyTopicCreate
    from app.services import study_topics as svc
    await _seed_course(db_conn, "STA")
    await svc.create_study_topic(SENTINEL_USER_ID, StudyTopicCreate(
        course_code="STA", name="open-topic", status="not_started",
    ))
    await svc.create_study_topic(SENTINEL_USER_ID, StudyTopicCreate(
        course_code="STA", name="done-topic", status="studied",
    ))
    studied_only = await svc.list_study_topics(SENTINEL_USER_ID, status="studied")
    assert len(studied_only) == 1
    assert studied_only[0].status == "studied"
    assert studied_only[0].name == "done-topic"


@pytest.mark.asyncio
async def test_update_study_topic(client, db_conn):
    from app.schemas import StudyTopicCreate, StudyTopicPatch
    from app.services import study_topics as svc
    await _seed_course(db_conn, "UPD")
    created = await svc.create_study_topic(SENTINEL_USER_ID, StudyTopicCreate(
        course_code="UPD", name="Original", status="not_started",
    ))
    updated = await svc.update_study_topic(
        SENTINEL_USER_ID, created.id, StudyTopicPatch(name="Renamed", confidence=4)
    )
    assert updated.name == "Renamed"
    assert updated.confidence == 4
    assert updated.id == created.id
    # last_reviewed_at not set when status not in studied/mastered
    assert updated.last_reviewed_at is None


@pytest.mark.asyncio
async def test_update_study_topic_studied_sets_last_reviewed_at(client, db_conn):
    from app.schemas import StudyTopicCreate, StudyTopicPatch
    from app.services import study_topics as svc
    await _seed_course(db_conn, "STD")
    created = await svc.create_study_topic(SENTINEL_USER_ID, StudyTopicCreate(
        course_code="STD", name="To-review", status="not_started",
    ))
    assert created.last_reviewed_at is None
    updated = await svc.update_study_topic(
        SENTINEL_USER_ID, created.id, StudyTopicPatch(status="studied")
    )
    assert updated.status == "studied"
    assert updated.last_reviewed_at is not None


@pytest.mark.asyncio
async def test_update_study_topic_mastered_sets_last_reviewed_at(client, db_conn):
    from app.schemas import StudyTopicCreate, StudyTopicPatch
    from app.services import study_topics as svc
    await _seed_course(db_conn, "MST")
    created = await svc.create_study_topic(SENTINEL_USER_ID, StudyTopicCreate(
        course_code="MST", name="Master-this",
    ))
    updated = await svc.update_study_topic(
        SENTINEL_USER_ID, created.id, StudyTopicPatch(status="mastered")
    )
    assert updated.status == "mastered"
    assert updated.last_reviewed_at is not None


@pytest.mark.asyncio
async def test_update_study_topic_empty_patch_raises(client, db_conn):
    from app.schemas import StudyTopicPatch
    from app.services import study_topics as svc
    with pytest.raises(ValueError):
        await svc.update_study_topic(
            SENTINEL_USER_ID,
            "00000000-0000-0000-0000-000000000000",
            StudyTopicPatch(),
        )


@pytest.mark.asyncio
async def test_update_study_topic_missing_id_raises(client, db_conn):
    from app.schemas import StudyTopicPatch
    from app.services import study_topics as svc
    with pytest.raises(ValueError):
        await svc.update_study_topic(
            SENTINEL_USER_ID,
            "00000000-0000-0000-0000-000000000000",
            StudyTopicPatch(name="ghost"),
        )


@pytest.mark.asyncio
async def test_delete_study_topic(client, db_conn):
    from app.schemas import StudyTopicCreate
    from app.services import study_topics as svc
    await _seed_course(db_conn, "DEL")
    created = await svc.create_study_topic(SENTINEL_USER_ID, StudyTopicCreate(
        course_code="DEL", name="Doomed",
    ))
    await svc.delete_study_topic(SENTINEL_USER_ID, created.id)
    result = await svc.list_study_topics(SENTINEL_USER_ID, course_code="DEL")
    assert result == []


@pytest.mark.asyncio
async def test_add_lecture_topics_with_existing_lecture_id(client, db_conn):
    """Bulk-insert topics linked to an existing lecture (no auto-create)."""
    from app.schemas import LectureCreate, LectureTopicsAdd
    from app.services import lectures as lectures_svc
    from app.services import study_topics as svc
    await _seed_course(db_conn, "LEC")
    lec = await lectures_svc.create_lecture(SENTINEL_USER_ID, LectureCreate(
        course_code="LEC", number=1, held_on=date(2026, 4, 10), kind="lecture",
        title="Wk1",
    ))
    payload = LectureTopicsAdd(
        course_code="LEC",
        covered_on=date(2026, 4, 10),
        kind="lecture",
        topics=[
            {"chapter": "1", "name": "Topic A", "sort_order": 0},
            {"chapter": "1", "name": "Topic B", "status": "in_progress"},
            {"name": "Topic C"},
        ],
        lecture_id=lec.id,
    )
    inserted = await svc.add_lecture_topics(SENTINEL_USER_ID, payload)
    assert len(inserted) == 3
    names = {t.name for t in inserted}
    assert names == {"Topic A", "Topic B", "Topic C"}
    for t in inserted:
        assert t.course_code == "LEC"
        assert t.lecture_id == lec.id
        assert t.kind == "lecture"
        assert t.covered_on == date(2026, 4, 10)
    in_progress = [t for t in inserted if t.name == "Topic B"][0]
    assert in_progress.status == "in_progress"
    # The two without explicit status should default to "not_started"
    other = [t for t in inserted if t.name in ("Topic A", "Topic C")]
    for t in other:
        assert t.status == "not_started"


@pytest.mark.asyncio
async def test_add_lecture_topics_auto_creates_lecture(client, db_conn):
    """When create_lecture is set and no lecture_id, auto-create the lecture."""
    from app.schemas import LectureCreate, LectureTopicsAdd
    from app.services import lectures as lectures_svc
    from app.services import study_topics as svc
    await _seed_course(db_conn, "AUT")
    payload = LectureTopicsAdd(
        course_code="AUT",
        covered_on=date(2026, 4, 12),
        kind="lecture",
        topics=[
            {"name": "Auto1"},
            {"name": "Auto2", "sort_order": 1},
        ],
        create_lecture=LectureCreate(
            course_code="AUT",
            number=2,
            held_on=date(2026, 4, 12),
            kind="lecture",
            title="Auto-week",
        ),
    )
    inserted = await svc.add_lecture_topics(SENTINEL_USER_ID, payload)
    assert len(inserted) == 2
    # All inserted topics should share the same lecture_id (auto-created)
    lecture_ids = {t.lecture_id for t in inserted}
    assert len(lecture_ids) == 1
    new_lecture_id = next(iter(lecture_ids))
    assert new_lecture_id is not None
    # Verify the lecture row actually exists
    fetched = await lectures_svc.get_lecture(SENTINEL_USER_ID, new_lecture_id)
    assert fetched is not None
    assert fetched.course_code == "AUT"
    assert fetched.number == 2
    assert fetched.title == "Auto-week"
