"""MCP tool tests — events entity (2 tools).

Coverage: list_events, record_event.

Note: events ordering uses `clock_timestamp()` (Phase 1 fix) so events
recorded back-to-back in one transaction still get distinct timestamps.
"""
import pytest
from unittest.mock import AsyncMock

from tests.mcp._harness import get_tool_fn


@pytest.mark.asyncio
async def test_list_events_empty(client, db_conn, mcp_server):
    list_events = get_tool_fn(mcp_server, "list_events")
    result = await list_events()
    assert result == []


@pytest.mark.asyncio
async def test_record_then_list(client, db_conn, mcp_server):
    record_event = get_tool_fn(mcp_server, "record_event")
    list_events = get_tool_fn(mcp_server, "list_events")

    recorded = await record_event(kind="evt:mcp:test", payload={"n": 1})
    assert recorded["kind"] == "evt:mcp:test"
    assert recorded["payload"] == {"n": 1}

    listed = await list_events()
    assert len(listed) == 1
    assert listed[0]["kind"] == "evt:mcp:test"
    assert listed[0]["payload"] == {"n": 1}


@pytest.mark.asyncio
async def test_list_events_filtered_by_kind(client, db_conn, mcp_server):
    record_event = get_tool_fn(mcp_server, "record_event")
    list_events = get_tool_fn(mcp_server, "list_events")

    await record_event(kind="evt:mcp:alpha", payload={"k": "a"})
    await record_event(kind="evt:mcp:beta", payload={"k": "b"})

    all_events = await list_events()
    assert len(all_events) == 2

    only_alpha = await list_events(kind="evt:mcp:alpha")
    assert len(only_alpha) == 1
    assert only_alpha[0]["kind"] == "evt:mcp:alpha"
    assert only_alpha[0]["payload"] == {"k": "a"}


# ── P2 closers ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_record_event_service_error_propagates(monkeypatch, client, db_conn, mcp_server):
    """If the service layer raises, the MCP wrapper does NOT swallow it.

    The current implementation has no try/except around the service call —
    this test locks in that the caller sees the error rather than receiving
    a silent ok=False response.
    """
    import app.services.events as events_svc

    record_event = get_tool_fn(mcp_server, "record_event")
    monkeypatch.setattr(events_svc, "record_event", AsyncMock(side_effect=ValueError("db exploded")))

    with pytest.raises(ValueError, match="db exploded"):
        await record_event(kind="evt:test:fail")


@pytest.mark.asyncio
async def test_list_events_filtered_by_since(client, db_conn, mcp_server):
    """list_events(since=...) returns only events at or after the cutoff.

    The service uses `created_at >= since` (inclusive). We record two events;
    clock_timestamp() gives each a distinct microsecond-precision timestamp
    even within the same transaction. We use the second event's own
    created_at as the `since` cutoff, which means:
      - second event is included (created_at == since, satisfies >=)
      - first event is excluded  (created_at < since, strictly earlier)
    """
    record_event = get_tool_fn(mcp_server, "record_event")
    list_events = get_tool_fn(mcp_server, "list_events")

    await record_event(kind="evt:mcp:older", payload={"seq": 1})
    newer = await record_event(kind="evt:mcp:newer", payload={"seq": 2})

    # Use the newer event's own timestamp as the cutoff (inclusive >=).
    cutoff = newer["created_at"]
    filtered = await list_events(since=cutoff)
    kinds = [e["kind"] for e in filtered]

    assert "evt:mcp:newer" in kinds, "newer event must be included (created_at == since)"
    assert "evt:mcp:older" not in kinds, "older event must be excluded (created_at < since)"


@pytest.mark.asyncio
async def test_list_events_filtered_by_course_code(client, db_conn, mcp_server):
    """list_events(course_code=...) returns only events tagged to that course."""
    record_event = get_tool_fn(mcp_server, "record_event")
    list_events = get_tool_fn(mcp_server, "list_events")
    create_course = get_tool_fn(mcp_server, "create_course")

    # Create the course so the FK is satisfied.
    await create_course(code="EVTC1", full_name="Events Course 1")

    await record_event(kind="evt:mcp:tagged", course_code="EVTC1", payload={"n": 1})
    await record_event(kind="evt:mcp:untagged", payload={"n": 2})

    tagged = await list_events(course_code="EVTC1")
    assert len(tagged) == 1
    assert tagged[0]["kind"] == "evt:mcp:tagged"
    assert tagged[0]["course_code"] == "EVTC1"
