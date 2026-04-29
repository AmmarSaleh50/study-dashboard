"""MCP tool tests — events entity (2 tools).

Coverage: list_events, record_event.

Note: events ordering uses `clock_timestamp()` (Phase 1 fix) so events
recorded back-to-back in one transaction still get distinct timestamps.
"""
import pytest

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
