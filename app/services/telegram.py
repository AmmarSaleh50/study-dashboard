"""Telegram bot command dispatcher.

Phase 0: extracted from app/routers/internal.py with no behaviour change.
Phase 6: per-user chat_id -> user_id lookup happens before dispatch;
commands operate on the caller's data.
"""
import logging
import os
from pathlib import Path

import httpx

log = logging.getLogger(__name__)

# Shared pause flag for the Moodle scrape cron. Lives on the bind-mounted
# course-files directory so both this container and the n8n container can
# see it (n8n sees the same file at /var/courses/.moodle_cron_paused).
# When present, n8n's schedule-triggered runs skip the scrape; manual /sync
# via webhook always runs regardless.
PAUSE_FLAG = Path(os.environ.get("STUDY_ROOT", "/opt/courses")) / ".moodle_cron_paused"


async def _send_telegram(token: str, chat_id: int, text: str) -> None:
    async with httpx.AsyncClient(timeout=10) as client:
        await client.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
        )


async def handle_command(text: str, chat_id: int) -> str:
    """Run a Telegram /command, return the reply text.

    Commands today: /start, /help, /sync, /pause, /resume, /status (+ unknown
    command fallback). Behaviour preserved exactly from app/routers/internal.py.

    For /sync the function sends an immediate 'Syncing…' message directly via
    _send_telegram (because the n8n call can take up to 120 s) and returns ''
    on success — the n8n workflow sends its own rich summary at the end of the
    run. The router must skip sending the reply when it is an empty string.
    """
    cmd = text.split()[0].lower()

    if cmd in ("/start", "/help"):
        state = "⏸ paused" if PAUSE_FLAG.exists() else "▶ active"
        return (
            "OpenStudy bot — available commands:\n"
            "/sync — pull new files from Moodle now (~8s, works whether paused or not)\n"
            "/pause — pause the 30-min auto-cron\n"
            "/resume — re-enable the 30-min auto-cron\n"
            "/status — show cron state\n"
            "/help — this message\n"
            "\n"
            f"Cron currently: {state}"
        )

    if cmd == "/sync":
        webhook_url = os.environ.get("N8N_MOODLE_WEBHOOK_URL", "").strip()
        if not webhook_url:
            return "Sync unavailable: N8N_MOODLE_WEBHOOK_URL is not configured."
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        # Send immediate feedback before the long-running HTTP call.
        if token:
            await _send_telegram(token, chat_id, "\U0001f504 Syncing with Moodle…")
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.get(webhook_url)
            if resp.status_code >= 400:
                return f"❌ Sync webhook returned HTTP {resp.status_code}"
        except Exception as exc:
            return f"❌ Sync failed: {exc}"
        # n8n sends its own rich summary; bot stays quiet on success.
        return ""

    if cmd == "/pause":
        try:
            PAUSE_FLAG.parent.mkdir(parents=True, exist_ok=True)
            PAUSE_FLAG.touch()
            return (
                "⏸ Moodle cron paused. The 30-min auto-cron is suspended.\n"
                "Use /sync to scrape now, /resume to re-enable."
            )
        except Exception as exc:
            return f"❌ Could not write pause flag: {exc}"

    if cmd == "/resume":
        try:
            PAUSE_FLAG.unlink(missing_ok=True)
            return "▶ Moodle cron resumed. Will fire on the next 30-min interval."
        except Exception as exc:
            return f"❌ Could not remove pause flag: {exc}"

    if cmd == "/status":
        paused = PAUSE_FLAG.exists()
        state = "⏸ paused" if paused else "▶ active"
        flag_info = f"flag at {PAUSE_FLAG}" if paused else "no pause flag"
        return f"\U0001f4ca Moodle cron: {state}\n{flag_info}"

    return f"Unknown command: {cmd}\nTry /help"
