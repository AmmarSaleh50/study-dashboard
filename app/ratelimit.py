"""DB-backed rate limiter for /auth/* endpoints.

Today: covers /auth/login. Phase 3 extends to /auth/signup, /auth/forgot.
Per-IP only today — Phase 3 adds per-account lockout.
"""
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import HTTPException, Request, status

from . import db
from .config import get_settings


Kind = Literal["login", "signup", "reset"]


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


async def check_auth_rate(request: Request, kind: Kind = "login") -> None:
    s = get_settings()
    ip = client_ip(request)
    since = datetime.now(timezone.utc) - timedelta(minutes=s.login_attempts_window_min)
    failures = await db.fetchval(
        "SELECT count(*) FROM auth_attempts "
        "WHERE ip = %s AND kind = %s AND ok = false AND at >= %s",
        ip, kind, since,
    )
    failures = failures or 0
    if failures >= s.login_attempts_max:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"too many {kind} attempts; try again in {s.login_attempts_window_min} min",
        )


async def record_auth_attempt(request: Request, ok: bool, kind: Kind = "login") -> None:
    ip = client_ip(request)
    ua = request.headers.get("user-agent", "")[:200]
    await db.execute(
        "INSERT INTO auth_attempts (ip, ok, kind, user_agent) VALUES (%s, %s, %s, %s)",
        ip, ok, kind, ua,
    )


# Back-compat aliases — let existing /auth/login callers continue to use the
# old names. Removed in Phase 3 once signup endpoint exists.
check_login_rate = check_auth_rate
record_login_attempt = record_auth_attempt
