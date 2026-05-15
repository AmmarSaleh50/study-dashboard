from datetime import datetime, timezone, timedelta
from typing import Optional

import pyotp
from fastapi import Cookie, HTTPException, Response, status
from itsdangerous import TimestampSigner, BadSignature, SignatureExpired
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from . import db
from .config import get_settings

COOKIE_NAME = "study_session"
_ph = PasswordHasher()


def _signer() -> TimestampSigner:
    return TimestampSigner(get_settings().session_secret)


def hash_password(plain: str) -> str:
    """Argon2id hash — for the offline password-hashing CLI."""
    return _ph.hash(plain)


def verify_password(plain: str) -> bool:
    s = get_settings()
    if not s.app_password_hash:
        return False
    try:
        _ph.verify(s.app_password_hash, plain)
        return True
    except VerifyMismatchError:
        return False
    except Exception:
        return False


def issue_session(response: Response) -> None:
    s = get_settings()
    token = _signer().sign(b"authed").decode()
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=s.session_ttl_days * 24 * 60 * 60,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )


def clear_session(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")


def _verify_cookie(cookie_value: Optional[str], max_age_sec: int) -> bool:
    if not cookie_value:
        return False
    try:
        _signer().unsign(cookie_value.encode(), max_age=max_age_sec)
        return True
    except (BadSignature, SignatureExpired):
        return False


async def optional_auth(
    study_session: Optional[str] = Cookie(default=None, alias=COOKIE_NAME),
) -> bool:
    s = get_settings()
    return _verify_cookie(study_session, s.session_ttl_days * 24 * 60 * 60)


async def require_auth(
    study_session: Optional[str] = Cookie(default=None, alias=COOKIE_NAME),
) -> bool:
    ok = await optional_auth(study_session)
    if not ok:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not authenticated")
    return True


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def in_window(dt: datetime, minutes: int) -> bool:
    return dt >= utcnow() - timedelta(minutes=minutes)


# ── TOTP (RFC 6238) ─────────────────────────────────────────────────────────

async def get_totp_state() -> tuple[bool, Optional[str]]:
    """Compatibility shim — delegates to app.services.totp."""
    from .services import totp as totp_svc
    return await totp_svc.get_state()


async def is_totp_required() -> bool:
    enabled, secret = await get_totp_state()
    return enabled and bool(secret)


async def verify_totp(code: Optional[str]) -> bool:
    if not code:
        return False
    code = code.strip().replace(" ", "")
    if not code.isdigit() or len(code) != 6:
        return False
    enabled, secret = await get_totp_state()
    if not enabled or not secret:
        return False
    return pyotp.TOTP(secret).verify(code, valid_window=1)
