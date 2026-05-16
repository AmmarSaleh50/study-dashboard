"""Dashboard intents — single entry point for both REST and MCP callers."""
from uuid import UUID

from ..schemas import DashboardSummary
from ..services import dashboard as svc


async def get_dashboard_summary(user_id: UUID) -> DashboardSummary:
    return await svc.get_dashboard_summary(user_id)
