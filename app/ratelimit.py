"""Simple DB-backed rate limiter for /login.

We record each attempt (ip, at, ok). If too many failed attempts from a single IP
within the window, reject with 429.
"""
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request, status

from . import db
from .config import get_settings


def client_ip(request: Request) -> str:
    # Cloudflare sets `CF-Connecting-IP` to the real client IP at the edge
    # and overrides anything the client supplied — preferred because it
    # can't be spoofed. An attacker rotating `X-Forwarded-For` would
    # otherwise bypass the rate limiter, since CF appends to (not strips)
    # client-supplied XFF.
    cf = request.headers.get("cf-connecting-ip")
    if cf:
        return cf.strip()
    # Fallback for non-Cloudflare deploys: trust XFF only if it has no
    # commas (single trusted proxy hop). With a chain longer than that,
    # we can't tell trusted entries from attacker-controlled ones, so we
    # collapse to the connection IP — globally rate-limiting is better
    # than letting a header-flipping attacker bypass the limit entirely.
    xff = request.headers.get("x-forwarded-for")
    if xff and "," not in xff:
        return xff.strip()
    if request.client:
        return request.client.host
    return "unknown"


async def check_login_rate(request: Request) -> None:
    s = get_settings()
    ip = client_ip(request)
    since = datetime.now(timezone.utc) - timedelta(minutes=s.login_attempts_window_min)

    failures = await db.fetchval(
        "SELECT count(*) FROM login_attempts "
        "WHERE ip = %s AND ok = false AND at >= %s",
        ip, since,
    )
    failures = failures or 0
    if failures >= s.login_attempts_max:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"too many login attempts; try again in {s.login_attempts_window_min} min",
        )


async def record_login_attempt(request: Request, ok: bool) -> None:
    ip = client_ip(request)
    ua = request.headers.get("user-agent", "")[:200]
    await db.execute(
        "INSERT INTO login_attempts (ip, ok, user_agent) VALUES (%s, %s, %s)",
        ip, ok, ua,
    )
