from fastapi import APIRouter, Depends

from ..auth import require_auth, SENTINEL_USER_ID
from ..schemas import AppSettings, AppSettingsPatch
from ..intents import settings as intent

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=AppSettings)
async def get(_: bool = Depends(require_auth)) -> AppSettings:
    return await intent.get_settings(SENTINEL_USER_ID)


@router.patch("", response_model=AppSettings)
async def patch(body: AppSettingsPatch, _: bool = Depends(require_auth)) -> AppSettings:
    return await intent.update_settings(SENTINEL_USER_ID, body)
