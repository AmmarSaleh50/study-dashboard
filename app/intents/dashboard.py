"""Dashboard intents — single entry point for both REST and MCP callers.

Today: thin pass-through to app.services.dashboard. The user_id parameter
is accepted but ignored until Phase 2 wires up per-user filtering.
"""
from uuid import UUID

from ..schemas import DashboardSummary
from ..services import dashboard as svc


async def get_dashboard_summary(user_id: UUID) -> DashboardSummary:
    return await svc.get_dashboard_summary()
