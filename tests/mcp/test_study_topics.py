"""MCP tool tests — study_topic entity (7 tools).

Coverage: list_study_topics, create_study_topic, update_study_topic,
mark_studied, set_confidence, add_lecture_topics, delete_study_topic.
"""
import pytest

from tests.mcp._harness import get_tool_fn


@pytest.mark.asyncio
async def test_list_study_topics_empty(client, db_conn, mcp_server):
    list_study_topics = get_tool_fn(mcp_server, "list_study_topics")
    result = await list_study_topics()
    assert result == []


@pytest.mark.asyncio
async def test_create_then_list(client, db_conn, mcp_server):
    create_course = get_tool_fn(mcp_server, "create_course")
    create_study_topic = get_tool_fn(mcp_server, "create_study_topic")
    list_study_topics = get_tool_fn(mcp_server, "list_study_topics")

    await create_course(code="STA", full_name="Study Topics A", ects=5)
    created = await create_study_topic(
        course_code="STA",
        name="Limits and continuity",
        chapter="1",
    )
    assert created["course_code"] == "STA"
    assert created["name"] == "Limits and continuity"
    assert created["status"] == "not_started"

    listed = await list_study_topics(course_code="STA")
    assert len(listed) == 1
    assert listed[0]["name"] == "Limits and continuity"


@pytest.mark.asyncio
async def test_update_study_topic(client, db_conn, mcp_server):
    create_course = get_tool_fn(mcp_server, "create_course")
    create_study_topic = get_tool_fn(mcp_server, "create_study_topic")
    update_study_topic = get_tool_fn(mcp_server, "update_study_topic")

    await create_course(code="STB", full_name="Study Topics B", ects=4)
    created = await create_study_topic(course_code="STB", name="Original name")
    topic_id = created["id"]

    updated = await update_study_topic(topic_id=topic_id, name="Renamed")
    assert updated["name"] == "Renamed"
    assert updated["course_code"] == "STB"


@pytest.mark.asyncio
async def test_update_status_studied_sets_last_reviewed_at(client, db_conn, mcp_server):
    create_course = get_tool_fn(mcp_server, "create_course")
    create_study_topic = get_tool_fn(mcp_server, "create_study_topic")
    update_study_topic = get_tool_fn(mcp_server, "update_study_topic")

    await create_course(code="STC", full_name="Study Topics C", ects=3)
    created = await create_study_topic(course_code="STC", name="Derivatives")
    assert created.get("last_reviewed_at") in (None, "")

    updated = await update_study_topic(topic_id=created["id"], status="studied")
    assert updated["status"] == "studied"
    assert updated.get("last_reviewed_at"), "last_reviewed_at should be stamped on status='studied'"


@pytest.mark.asyncio
async def test_mark_studied(client, db_conn, mcp_server):
    create_course = get_tool_fn(mcp_server, "create_course")
    create_study_topic = get_tool_fn(mcp_server, "create_study_topic")
    mark_studied = get_tool_fn(mcp_server, "mark_studied")

    await create_course(code="STD", full_name="Study Topics D", ects=3)
    created = await create_study_topic(course_code="STD", name="Integration by parts")

    result = await mark_studied(topic_id=created["id"])
    assert result["status"] == "studied"
    assert result.get("last_reviewed_at"), "mark_studied should stamp last_reviewed_at"


@pytest.mark.asyncio
async def test_set_confidence_valid(client, db_conn, mcp_server):
    create_course = get_tool_fn(mcp_server, "create_course")
    create_study_topic = get_tool_fn(mcp_server, "create_study_topic")
    set_confidence = get_tool_fn(mcp_server, "set_confidence")

    await create_course(code="STE", full_name="Study Topics E", ects=3)
    created = await create_study_topic(course_code="STE", name="Eigenvalues")

    result = await set_confidence(topic_id=created["id"], confidence=3)
    assert result["confidence"] == 3


@pytest.mark.asyncio
async def test_set_confidence_out_of_range_raises(client, db_conn, mcp_server):
    create_course = get_tool_fn(mcp_server, "create_course")
    create_study_topic = get_tool_fn(mcp_server, "create_study_topic")
    set_confidence = get_tool_fn(mcp_server, "set_confidence")

    await create_course(code="STF", full_name="Study Topics F", ects=3)
    created = await create_study_topic(course_code="STF", name="Bayes' theorem")
    topic_id = created["id"]

    with pytest.raises(ValueError, match="0..5"):
        await set_confidence(topic_id=topic_id, confidence=-1)

    with pytest.raises(ValueError, match="0..5"):
        await set_confidence(topic_id=topic_id, confidence=6)


@pytest.mark.asyncio
async def test_add_lecture_topics_with_existing_lecture_id(client, db_conn, mcp_server):
    create_course = get_tool_fn(mcp_server, "create_course")
    create_lecture = get_tool_fn(mcp_server, "create_lecture")
    add_lecture_topics = get_tool_fn(mcp_server, "add_lecture_topics")
    list_study_topics = get_tool_fn(mcp_server, "list_study_topics")

    await create_course(code="STG", full_name="Study Topics G", ects=4)
    lecture = await create_lecture(
        course_code="STG",
        number=1,
        held_on="2026-04-15",
        kind="lecture",
        title="Intro session",
    )
    lecture_id = lecture["id"]

    inserted = await add_lecture_topics(
        course_code="STG",
        covered_on="2026-04-15",
        lecture_id=lecture_id,
        topics=[
            {"name": "Topic alpha", "chapter": "1.1"},
            {"name": "Topic beta", "chapter": "1.2"},
        ],
    )
    assert len(inserted) == 2
    assert all(t["lecture_id"] == lecture_id for t in inserted)
    assert {t["name"] for t in inserted} == {"Topic alpha", "Topic beta"}

    listed = await list_study_topics(course_code="STG")
    assert len(listed) == 2


@pytest.mark.asyncio
async def test_add_lecture_topics_creates_lecture(client, db_conn, mcp_server):
    create_course = get_tool_fn(mcp_server, "create_course")
    add_lecture_topics = get_tool_fn(mcp_server, "add_lecture_topics")
    list_lectures = get_tool_fn(mcp_server, "list_lectures")
    list_study_topics = get_tool_fn(mcp_server, "list_study_topics")

    await create_course(code="STH", full_name="Study Topics H", ects=4)

    inserted = await add_lecture_topics(
        course_code="STH",
        covered_on="2026-04-20",
        create_lecture_number=1,
        create_lecture_title="Auto-created lecture",
        topics=[
            {"name": "Auto topic 1"},
            {"name": "Auto topic 2"},
        ],
    )
    assert len(inserted) == 2
    new_lecture_id = inserted[0]["lecture_id"]
    assert new_lecture_id is not None
    assert all(t["lecture_id"] == new_lecture_id for t in inserted)

    lectures = await list_lectures(course_code="STH")
    assert len(lectures) == 1
    assert lectures[0]["id"] == new_lecture_id
    assert lectures[0]["title"] == "Auto-created lecture"

    topics = await list_study_topics(course_code="STH")
    assert len(topics) == 2


@pytest.mark.asyncio
async def test_delete_study_topic(client, db_conn, mcp_server):
    create_course = get_tool_fn(mcp_server, "create_course")
    create_study_topic = get_tool_fn(mcp_server, "create_study_topic")
    delete_study_topic = get_tool_fn(mcp_server, "delete_study_topic")
    list_study_topics = get_tool_fn(mcp_server, "list_study_topics")

    await create_course(code="STI", full_name="Study Topics I", ects=3)
    created = await create_study_topic(course_code="STI", name="Doomed topic")
    topic_id = created["id"]
    assert len(await list_study_topics(course_code="STI")) == 1

    result = await delete_study_topic(topic_id=topic_id)
    assert result == {"deleted": topic_id}
    assert await list_study_topics(course_code="STI") == []
