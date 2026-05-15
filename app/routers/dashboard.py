from fastapi import APIRouter, Depends

from ..auth import require_auth, SENTINEL_USER_ID
from ..schemas import DashboardSummary
from ..intents import dashboard as intent

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardSummary)
async def dashboard(_: bool = Depends(require_auth)) -> DashboardSummary:
    return await intent.get_dashboard_summary(SENTINEL_USER_ID)
