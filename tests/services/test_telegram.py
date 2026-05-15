"""Tests for app/services/telegram.py — the bot command dispatcher.

Phase 0: extracted from app/routers/internal.py with no behaviour change.
Phase 6: per-user routing will key off chat_id lookup; the dispatch table
itself stays in this module.
"""
import pytest


@pytest.mark.asyncio
async def test_dispatch_unknown_command_returns_help_pointer():
    from app.services import telegram as svc
    out = await svc.handle_command("/notarealcommand", chat_id=1)
    assert isinstance(out, str)
    # Either includes "unknown" or includes the /help pointer.
    assert ("unknown" in out.lower()) or ("/help" in out.lower())


@pytest.mark.asyncio
async def test_dispatch_start_command_returns_greeting():
    from app.services import telegram as svc
    out = await svc.handle_command("/start", chat_id=1)
    assert isinstance(out, str)
    assert "openstudy" in out.lower() or "study" in out.lower()


@pytest.mark.asyncio
async def test_dispatch_help_command_lists_commands():
    from app.services import telegram as svc
    out = await svc.handle_command("/help", chat_id=1)
    assert isinstance(out, str)
    # /help should mention at least /sync and /pause.
    assert "/sync" in out
    assert "/pause" in out
