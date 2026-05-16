from fastapi import APIRouter, Depends

from ..auth import require_user, User
from ..schemas import AppSettings, AppSettingsPatch
from ..intents import settings as intent

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=AppSettings)
async def get(user: User = Depends(require_user)) -> AppSettings:
    return await intent.get_settings(user.id)


@router.patch("", response_model=AppSettings)
async def patch(body: AppSettingsPatch, user: User = Depends(require_user)) -> AppSettings:
    return await intent.update_settings(user.id, body)
