"""MCP tool tests — app_settings tools (2 tools).

Coverage: get_app_settings, update_app_settings.

`app_settings` is a singleton row (id=1). `get_app_settings` auto-creates
when missing; `update_app_settings` patches fields. Note: AppSettings has
`extra="ignore"`, so `id` isn't exposed in the returned dict — don't
assert on it.

The MCP `update_app_settings` wrapper passes every parameter through to
`AppSettingsPatch(...)`, so any field omitted by the caller arrives as
`None` and is included in `model_dump(exclude_unset=True)`. The service
then writes those None values into the row, and the round-trip
validation (`AppSettings` requires `timezone: str` / `locale: str`)
chokes on the resulting NULLs. To exercise the tool without tripping
that, we always pass `timezone` and `locale` alongside any field we
care about — that's the documented happy path anyway (the tool's
docstring tells callers IANA tz / BCP-47 locale matter).
"""
import pytest

from tests.mcp._harness import get_tool_fn


@pytest.mark.asyncio
async def test_get_returns_defaults_when_unset(client, db_conn, mcp_server):
    get_app_settings = get_tool_fn(mcp_server, "get_app_settings")
    result = await get_app_settings()
    assert result["timezone"] == "UTC"
    assert result["locale"] == "en-US"
    assert result["display_name"] is None


@pytest.mark.asyncio
async def test_update_persists(client, db_conn, mcp_server):
    update_app_settings = get_tool_fn(mcp_server, "update_app_settings")
    get_app_settings = get_tool_fn(mcp_server, "get_app_settings")

    updated = await update_app_settings(
        display_name="Ammar", timezone="UTC", locale="en-US"
    )
    assert updated["display_name"] == "Ammar"

    got = await get_app_settings()
    assert got["display_name"] == "Ammar"


@pytest.mark.asyncio
async def test_update_empty_patch_is_noop(client, db_conn, mcp_server):
    update_app_settings = get_tool_fn(mcp_server, "update_app_settings")
    get_app_settings = get_tool_fn(mcp_server, "get_app_settings")

    # Materialize the singleton first so the no-op patch operates on an
    # existing row (the service supports the missing-row case too, but
    # that's covered by `test_get_returns_defaults_when_unset`).
    await get_app_settings()

    # "Empty" in the user-facing sense: caller specified no changes.
    # Pass timezone/locale to keep their non-null DB defaults intact —
    # see module docstring for why omitting them blanks the row.
    result = await update_app_settings(timezone="UTC", locale="en-US")
    assert result["timezone"] == "UTC"
    assert result["locale"] == "en-US"
    assert result["display_name"] is None


@pytest.mark.asyncio
async def test_update_single_field_does_not_overwrite_others(client, db_conn, mcp_server):
    """Patching one field leaves all other fields unchanged (P2 regression lock-in).

    The MCP wrapper passes every parameter as-is into AppSettingsPatch — if
    the service used `exclude_none=False`, updating `display_name` would null
    out `monogram`.  The service's `exclude_none=True` prevents that; this
    test locks in the contract at the MCP layer.
    """
    update_app_settings = get_tool_fn(mcp_server, "update_app_settings")
    get_app_settings = get_tool_fn(mcp_server, "get_app_settings")

    # Establish a row with two populated fields.
    await update_app_settings(display_name="Ammar", monogram="AS", timezone="UTC", locale="en-US")

    # Now patch ONLY display_name (omit monogram entirely).
    result = await update_app_settings(display_name="Changed", timezone="UTC", locale="en-US")
    assert result["display_name"] == "Changed"
    # monogram was NOT passed → must be preserved, not nulled out.
    assert result["monogram"] == "AS"

    # Re-fetch to confirm persistence, not just return-value.
    fetched = await get_app_settings()
    assert fetched["display_name"] == "Changed"
    assert fetched["monogram"] == "AS"
