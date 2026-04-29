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
from pathlib import Path

import httpx
from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request, status

from ..services import file_index as file_index_svc

router = APIRouter(prefix="/internal", tags=["internal"])
log = logging.getLogger(__name__)

# Shared pause flag for the Moodle scrape cron. Lives on the bind-mounted
# course-files directory so both this container and the n8n container can
# see it (n8n sees the same file at /var/courses/.moodle_cron_paused).
# When present, n8n's schedule-triggered runs skip the scrape; manual /sync
# via webhook always runs regardless.
PAUSE_FLAG = Path(os.environ.get("STUDY_ROOT", "/opt/courses")) / ".moodle_cron_paused"


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


async def _send_telegram(token: str, chat_id: int, text: str) -> None:
    async with httpx.AsyncClient(timeout=10) as client:
        await client.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
        )


@router.post("/telegram")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None, alias="X-Telegram-Bot-Api-Secret-Token"),
):
    """Receive incoming messages from Telegram and respond to bot commands.

    Authenticated by Telegram's own `X-Telegram-Bot-Api-Secret-Token` header,
    which Telegram includes on every webhook delivery if we set it via setWebhook.
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

    # Allowlist: only respond to the operator's own chat (TELEGRAM_CHAT_ID)
    allowed = int(os.environ.get("TELEGRAM_CHAT_ID", "0") or "0")
    if chat_id != allowed:
        log.warning("telegram webhook from unauthorised chat_id=%s", chat_id)
        return {"ok": True}  # silent ignore

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        return {"ok": False, "reason": "no bot token configured"}

    cmd = text.split()[0].lower()

    if cmd in ("/start", "/help"):
        state = "⏸ paused" if PAUSE_FLAG.exists() else "▶ active"
        await _send_telegram(token, chat_id,
            "Available commands:\n"
            "/sync — pull new files from Moodle now (~8s, works whether paused or not)\n"
            "/pause — pause the 30-min auto-cron\n"
            "/resume — re-enable the 30-min auto-cron\n"
            "/status — show cron state\n"
            "/help — this message\n"
            "\n"
            f"Cron currently: {state}"
        )
    elif cmd == "/sync":
        webhook_url = os.environ.get("N8N_MOODLE_WEBHOOK_URL", "").strip()
        if not webhook_url:
            await _send_telegram(token, chat_id,
                "Sync unavailable: N8N_MOODLE_WEBHOOK_URL is not configured.")
            return {"ok": True}
        # The n8n workflow sends its own rich HTML summary at the end of the
        # run (same format as the scheduled cron). Bot stays quiet on success
        # to avoid a redundant short summary; only "🔄 Syncing…" up front for
        # instant feedback, plus error handling if the webhook itself breaks.
        await _send_telegram(token, chat_id, "🔄 Syncing with Moodle…")
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.get(webhook_url)
            if resp.status_code >= 400:
                await _send_telegram(token, chat_id,
                    f"❌ Sync webhook returned HTTP {resp.status_code}")
        except Exception as exc:
            await _send_telegram(token, chat_id, f"❌ Sync failed: {exc}")
    elif cmd == "/pause":
        try:
            PAUSE_FLAG.parent.mkdir(parents=True, exist_ok=True)
            PAUSE_FLAG.touch()
            await _send_telegram(token, chat_id,
                "⏸ Moodle cron paused. The 30-min auto-cron is suspended.\n"
                "Use /sync to scrape now, /resume to re-enable.")
        except Exception as exc:
            await _send_telegram(token, chat_id, f"❌ Could not write pause flag: {exc}")
    elif cmd == "/resume":
        try:
            PAUSE_FLAG.unlink(missing_ok=True)
            await _send_telegram(token, chat_id,
                "▶ Moodle cron resumed. Will fire on the next 30-min interval.")
        except Exception as exc:
            await _send_telegram(token, chat_id, f"❌ Could not remove pause flag: {exc}")
    elif cmd == "/status":
        paused = PAUSE_FLAG.exists()
        state = "⏸ paused" if paused else "▶ active"
        flag_info = f"flag at {PAUSE_FLAG}" if paused else "no pause flag"
        await _send_telegram(token, chat_id,
            f"📊 Moodle cron: {state}\n{flag_info}"
        )
    else:
        await _send_telegram(token, chat_id, f"Unknown command: {cmd}\nTry /help")

    return {"ok": True}
