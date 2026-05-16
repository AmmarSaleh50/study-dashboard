"""Settings intents — single entry point for both REST and MCP callers.

Pass-through to app.services.settings. The user_id parameter is forwarded to
the service, which filters by it via WHERE user_id = $1.
"""
from uuid import UUID

from ..schemas import AppSettings, AppSettingsPatch
from ..services import settings as svc


async def get_settings(user_id: UUID) -> AppSettings:
    return await svc.get_settings(user_id)


async def update_settings(user_id: UUID, patch: AppSettingsPatch) -> AppSettings:
    return await svc.update_settings(user_id, patch)
