"""Internal endpoints not meant for end users.

Protected by a shared secret in the `X-Internal-Secret` header (configured
via `INTERNAL_API_SECRET`). Used by background jobs (n8n workflows, cron
scripts) to trigger server-side actions like reindexing or to deliver
inbound webhooks.

The `/telegram` endpoint is special: it's authenticated by Telegram's own
`X-Telegram-Bot-Api-Secret-Token` header instead of the shared secret.
"""
import logging
import os

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request, status

from ..auth import SENTINEL_USER_ID, set_current_user_id
from ..services import file_index as file_index_svc
from ..services import telegram as telegram_svc
from ..services import user_secrets as user_secrets_svc

router = APIRouter(prefix="/internal", tags=["internal"])
log = logging.getLogger(__name__)


def _check_secret(provided: str | None) -> None:
    expected = os.environ.get("INTERNAL_API_SECRET", "").strip()
    if not expected:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="INTERNAL_API_SECRET not configured on server")
    if not provided or provided.strip() != expected:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="bad secret")


async def _reindex() -> None:
    """Wrapper that swallows exceptions so background-task failures don't
    crash the worker. Errors are logged and surface in /api/health.

    BackgroundTasks accepts both sync and async callables — making this
    `async def` lets it await the now-async `index_all()` directly."""
    try:
        stats = await file_index_svc.index_all()
        log.info("file_index reindex done: %s", stats)
    except Exception as e:
        log.exception("file_index reindex failed: %s", e)


@router.post("/sync")
def trigger_sync(
    background: BackgroundTasks,
    mode: str = "sync",
    x_internal_secret: str | None = Header(default=None, alias="X-Internal-Secret"),
):
    """Queue a re-index of `STUDY_ROOT` for full-text search.

    The `mode` query param is accepted (and echoed back) for compatibility
    with callers that historically distinguished sync directions, but the
    only action this endpoint performs today is reindexing. Returns 200
    immediately; indexing runs as a FastAPI background task.
    """
    _check_secret(x_internal_secret)
    background.add_task(_reindex)
    return {"ok": True, "mode": mode, "queued": "reindex"}


@router.post("/index-files")
def trigger_index(
    background: BackgroundTasks,
    x_internal_secret: str | None = Header(default=None, alias="X-Internal-Secret"),
):
    """Queue a re-index of `STUDY_ROOT` for full-text search."""
    _check_secret(x_internal_secret)
    background.add_task(_reindex)
    return {"ok": True, "queued": "reindex"}



@router.post("/telegram")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None, alias="X-Telegram-Bot-Api-Secret-Token"),
):
    """Receive incoming messages from Telegram and respond to bot commands.

    Authenticated by Telegram's own `X-Telegram-Bot-Api-Secret-Token` header,
    which Telegram includes on every webhook delivery if we set it via setWebhook.

    Phase 6: routes to the correct user by looking up `chat_id` in
    `user_secrets.telegram_chat_id`.  Falls back to the operator sentinel when
    the chat_id matches `TELEGRAM_CHAT_ID` env but has no user_secrets row.
    """
    expected = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "").strip()
    if not expected or x_telegram_bot_api_secret_token != expected:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="bad webhook token")

    body = await request.json()
    msg = body.get("message") or {}
    chat_id = (msg.get("chat") or {}).get("id")
    text = (msg.get("text") or "").strip()

    if not chat_id or not text:
        return {"ok": True}

    # --- Phase 6: resolve user_id from chat_id ---------------------------
    user_id = await user_secrets_svc.get_user_id_by_chat_id(str(chat_id))

    if user_id is None:
        # Operator-legacy fallback: check TELEGRAM_CHAT_ID env.
        operator_chat_id = int(os.environ.get("TELEGRAM_CHAT_ID", "0") or "0")
        if chat_id == operator_chat_id:
            user_id = SENTINEL_USER_ID
        else:
            log.warning("telegram webhook from unrecognised chat_id=%s", chat_id)
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="chat_id not registered")

    # Stamp the resolved user onto the per-request contextvar so GUC / RLS
    # applies to any DB calls inside handle_command.
    set_current_user_id(user_id)

    reply = await telegram_svc.handle_command(text, chat_id=chat_id, user_id=user_id)

    # Send the reply using the user's own bot token (or env fallback).
    if reply:
        secrets = await user_secrets_svc.get_secrets(user_id)
        token = secrets.telegram_bot_token or os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        if token:
            await telegram_svc.send_message(token, chat_id, reply)

    return {"ok": True}
