"""Smoke test for app/intents/dashboard.py — proves the pass-through works.

Phase 2 will replace these with real per-user-scoping tests.
"""
import pytest
from uuid import UUID

OPERATOR = UUID("00000000-0000-0000-0000-000000000001")


@pytest.mark.asyncio
async def test_dashboard_intent_returns_summary(client, db_conn):
    from app.intents import dashboard as intent
    from app.schemas import DashboardSummary

    summary = await intent.get_dashboard_summary(OPERATOR)
    assert isinstance(summary, DashboardSummary)
    assert isinstance(summary.courses, list)
    assert isinstance(summary.tasks, list)
