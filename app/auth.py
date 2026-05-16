import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from functools import lru_cache
from typing import Optional
from uuid import UUID

import pyotp
from fastapi import Cookie, HTTPException, Response, status
from itsdangerous import TimestampSigner, BadSignature, SignatureExpired
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from . import db
from .config import get_settings


@dataclass(frozen=True)
class User:
    """Phase 0 placeholder. Phase 1 hydrates this from a users table read.

    The id is opaque to callers — pass it through to intents; the intents
    will use it for filtering once Phase 2 wires that up.
    """
    id: UUID
    email: str
    display_name: str


@lru_cache(maxsize=1)
def _sentinel_user() -> User:
    """Build the sentinel User from env-configured operator identity.

    Phase 1: env-driven defaults; the operator's row in the users table
    must match these values. Phase 3 makes user identity DB-driven via the
    session cookie payload.
    """
    s = get_settings()
    return User(
        id=UUID(s.operator_user_id),
        email=s.operator_email,
        display_name=s.operator_display_name,
    )


# Backwards-compat module-level constants. These resolve at import time
# from env; tests can re-import after env changes to pick up new values.
SENTINEL_USER_ID = UUID(get_settings().operator_user_id)

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


async def verify_password_for_user(email: str, plain: str) -> Optional[User]:
    """Look up user by email; argon2-verify; return User or None.

    Returns None for: unknown email, NULL password_hash, mismatch.
    """
    from . import db as db_module
    email = email.strip().lower()
    try:
        row = await db_module.fetchrow(
            "SELECT id, email, display_name, password_hash FROM users "
            "WHERE email = %s AND deleted_at IS NULL",
            email,
        )
    except Exception:
        return None
    if not row or not row.get("password_hash"):
        return None
    try:
        _ph.verify(row["password_hash"], plain)
    except VerifyMismatchError:
        return None
    except Exception:
        return None
    return User(
        id=row["id"] if isinstance(row["id"], UUID) else UUID(row["id"]),
        email=row["email"],
        display_name=row["display_name"],
    )


def issue_session(response: Response, user_id: UUID) -> None:
    s = get_settings()
    payload = json.dumps({"u": str(user_id), "iat": int(time.time())}).encode("utf-8")
    token = _signer().sign(payload).decode()
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


async def optional_user(
    study_session: Optional[str] = Cookie(default=None, alias=COOKIE_NAME),
) -> Optional[User]:
    """Phase 3: parses user_id out of the signed cookie payload and hydrates
    from the users table. Legacy `b"authed"` cookies fall back to the
    sentinel user (migration grace; Phase 5/6 can drop this).
    """
    if not study_session:
        return None
    s = get_settings()
    max_age = s.session_ttl_days * 24 * 60 * 60
    try:
        raw = _signer().unsign(study_session.encode(), max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None

    # Legacy: cookie signed b"authed" → return sentinel.
    if raw == b"authed":
        return _sentinel_user()

    # New: cookie signed JSON {u, iat}.
    try:
        data = json.loads(raw.decode("utf-8"))
        user_id = UUID(data["u"])
    except (json.JSONDecodeError, KeyError, ValueError):
        return None

    return await _load_user_from_db(user_id)


async def _load_user_from_db(user_id: UUID) -> Optional[User]:
    """Look up a user by id; return User dataclass or None if missing."""
    from . import db as db_module
    try:
        row = await db_module.fetchrow(
            "SELECT id, email, display_name FROM users WHERE id = %s AND deleted_at IS NULL",
            str(user_id),
        )
    except Exception:
        return None
    if not row:
        return None
    return User(
        id=row["id"] if isinstance(row["id"], UUID) else UUID(row["id"]),
        email=row["email"],
        display_name=row["display_name"],
    )


async def require_user(
    study_session: Optional[str] = Cookie(default=None, alias=COOKIE_NAME),
) -> User:
    """Like optional_user but raises 401 if not authed."""
    user = await optional_user(study_session)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not authenticated")
    return user


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def in_window(dt: datetime, minutes: int) -> bool:
    return dt >= utcnow() - timedelta(minutes=minutes)


# ── TOTP (RFC 6238) ─────────────────────────────────────────────────────────

async def get_totp_state() -> tuple[bool, Optional[str]]:
    """Compatibility shim — delegates to app.services.totp.

    Passes SENTINEL_USER_ID; Phase 3 will wire real user identity here.
    """
    from .services import totp as totp_svc
    return await totp_svc.get_state(SENTINEL_USER_ID)


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
