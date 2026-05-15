"""Settings intents — single entry point for both REST and MCP callers.

Today: thin pass-through to app.services.settings. The user_id parameter
is accepted but ignored until Phase 2 wires up per-user filtering.
"""
from uuid import UUID

from ..schemas import AppSettings, AppSettingsPatch
from ..services import settings as svc


async def get_settings(user_id: UUID) -> AppSettings:
    return await svc.get_settings()


async def update_settings(user_id: UUID, patch: AppSettingsPatch) -> AppSettings:
    return await svc.update_settings(patch)
