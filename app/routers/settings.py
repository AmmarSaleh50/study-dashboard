from fastapi import APIRouter, Depends

import httpx

from ..auth import require_user, User
from ..schemas import (
    AppSettings,
    AppSettingsPatch,
    SecretsPatch,
    SecretsStatus,
    TelegramTestResult,
)
from ..intents import settings as intent
from ..services import user_secrets as user_secrets_svc

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=AppSettings)
async def get(user: User = Depends(require_user)) -> AppSettings:
    return await intent.get_settings(user.id)


@router.patch("", response_model=AppSettings)
async def patch(body: AppSettingsPatch, user: User = Depends(require_user)) -> AppSettings:
    return await intent.update_settings(user.id, body)


# ── Per-user secrets (Telegram creds) ──────────────────────────────────────
#
# GET returns masked booleans only — decrypted secrets never leave the backend
# on the read path. PATCH supports per-field updates with empty-string clear
# semantics. POST /telegram/test sends a test message via the user's bot creds.


@router.get("/secrets", response_model=SecretsStatus)
async def get_secrets(user: User = Depends(require_user)) -> SecretsStatus:
    sec = await user_secrets_svc.get_secrets(user.id)
    return SecretsStatus(
        telegram_bot_token_set=sec.telegram_bot_token is not None,
        telegram_chat_id=sec.telegram_chat_id,
        telegram_webhook_secret_set=sec.telegram_webhook_secret is not None,
    )


@router.patch("/secrets", response_model=SecretsStatus)
async def patch_secrets(
    body: SecretsPatch, user: User = Depends(require_user)
) -> SecretsStatus:
    # Translate empty-string → clear; non-empty → set; None → no-op.
    kwargs: dict = {}
    if body.telegram_bot_token is not None:
        if body.telegram_bot_token == "":
            kwargs["clear_telegram_bot_token"] = True
        else:
            kwargs["telegram_bot_token"] = body.telegram_bot_token
    if body.telegram_chat_id is not None:
        if body.telegram_chat_id == "":
            kwargs["clear_telegram_chat_id"] = True
        else:
            kwargs["telegram_chat_id"] = body.telegram_chat_id
    if body.telegram_webhook_secret is not None:
        if body.telegram_webhook_secret == "":
            kwargs["clear_telegram_webhook_secret"] = True
        else:
            kwargs["telegram_webhook_secret"] = body.telegram_webhook_secret
    if kwargs:
        await user_secrets_svc.update_secrets(user.id, **kwargs)
    sec = await user_secrets_svc.get_secrets(user.id)
    return SecretsStatus(
        telegram_bot_token_set=sec.telegram_bot_token is not None,
        telegram_chat_id=sec.telegram_chat_id,
        telegram_webhook_secret_set=sec.telegram_webhook_secret is not None,
    )


@router.post("/telegram/test", response_model=TelegramTestResult)
async def telegram_test(user: User = Depends(require_user)) -> TelegramTestResult:
    """Send a 'OpenStudy test message' to the user's configured chat_id using
    their stored bot token. Returns ok=true on 200 from Telegram, otherwise
    ok=false with a human-readable error message."""
    sec = await user_secrets_svc.get_secrets(user.id)
    if not sec.telegram_bot_token:
        return TelegramTestResult(ok=False, message="Bot token not set.")
    if not sec.telegram_chat_id:
        return TelegramTestResult(ok=False, message="Chat ID not set.")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{sec.telegram_bot_token}/sendMessage",
                json={
                    "chat_id": sec.telegram_chat_id,
                    "text": "OpenStudy test message ✓",
                    "disable_web_page_preview": True,
                },
            )
    except Exception as exc:
        return TelegramTestResult(ok=False, message=f"Network error: {exc!s}"[:200])
    if resp.status_code == 200:
        return TelegramTestResult(ok=True)
    # Telegram error payloads look like {"ok": false, "error_code": 401, "description": "Unauthorized"}.
    try:
        body = resp.json()
        desc = body.get("description") or f"HTTP {resp.status_code}"
    except Exception:
        desc = f"HTTP {resp.status_code}"
    return TelegramTestResult(ok=False, message=str(desc)[:200])
