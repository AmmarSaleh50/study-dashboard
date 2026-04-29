from fastapi import APIRouter, Depends

from ..auth import require_auth
from ..schemas import DashboardSummary
from ..services.dashboard import get_dashboard_summary

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardSummary)
async def dashboard(_: bool = Depends(require_auth)) -> DashboardSummary:
    return await get_dashboard_summary()
