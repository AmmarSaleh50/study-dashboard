import pyotp
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from ..services import totp as totp_svc
from ..services import auth_signup as signup_svc
from ..auth import (
    SENTINEL_USER_ID,
    User,
    clear_session,
    is_totp_required,
    issue_session,
    optional_auth,
    require_auth,
    verify_password,
    verify_password_for_user,
    verify_totp,
    _sentinel_user,
)
from ..ratelimit import check_login_rate, record_login_attempt, check_auth_rate
from ..schemas import LoginRequest, SessionInfo, TotpSetupResponse, TotpVerifyRequest, SignupRequest, ForgotRequest, ResetRequest

router = APIRouter(prefix="/auth", tags=["auth"])


def _verify_totp_code(code: str, secret: str) -> bool:
    code = code.strip().replace(" ", "")
    if not code.isdigit() or len(code) != 6:
        return False
    return pyotp.TOTP(secret).verify(code, valid_window=1)


@router.post("/login", response_model=SessionInfo)
async def login(body: LoginRequest, request: Request, response: Response) -> SessionInfo:
    await check_login_rate(request)

    user: Optional[User] = None

    if body.email:
        # Email+password path: lookup + argon2 verify
        user = await verify_password_for_user(body.email, body.password)
    else:
        # Operator-legacy fallback: verify against APP_PASSWORD_HASH
        legacy_ok = verify_password(body.password)
        if legacy_ok:
            user = _sentinel_user()

    if user is None:
        await record_login_attempt(request, False)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")

    # TOTP check: per-user (totp service reads users.totp_*)
    enabled, secret = await totp_svc.get_state(user.id)
    if enabled and secret:
        if not body.totp_code:
            # Don't record as failed attempt — password was correct, user is
            # at the start of the two-factor flow.
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "totp_required")
        if not _verify_totp_code(body.totp_code, secret):
            await record_login_attempt(request, False)
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid totp code")

    await record_login_attempt(request, True)
    issue_session(response, user.id)
    return SessionInfo(authed=True, totp_enabled=bool(enabled))


@router.post("/logout", response_model=SessionInfo)
async def logout(response: Response) -> SessionInfo:
    clear_session(response)
    return SessionInfo(authed=False, totp_enabled=await is_totp_required())


@router.get("/session", response_model=SessionInfo)
async def session(authed: bool = Depends(optional_auth)) -> SessionInfo:
    return SessionInfo(authed=authed, totp_enabled=await is_totp_required())


# ── TOTP setup / disable (auth-gated) ──────────────────────────────────────

@router.post("/totp/setup", response_model=TotpSetupResponse)
async def totp_setup(_: bool = Depends(require_auth)) -> TotpSetupResponse:
    """Generate a fresh TOTP secret. Does NOT enable yet — must call /totp/enable
    with a valid code from an authenticator app first. The secret is stored on
    the singleton row but `totp_enabled` stays false until confirmed."""
    secret = pyotp.random_base32()
    # Upsert: on a fresh DB the singleton row may not exist yet, in which case
    # a bare UPDATE silently matches zero rows and the secret is lost — the
    # caller then sees 200 here but a 400 on /enable. Fixed via ON CONFLICT.
    await totp_svc.set_pending(SENTINEL_USER_ID, secret)
    uri = pyotp.TOTP(secret).provisioning_uri(name="admin", issuer_name="OpenStudy")
    return TotpSetupResponse(secret=secret, provisioning_uri=uri)


@router.post("/totp/enable", response_model=SessionInfo)
async def totp_enable(body: TotpVerifyRequest, _: bool = Depends(require_auth)) -> SessionInfo:
    """Confirm setup by submitting a 6-digit code from the authenticator."""
    enabled, secret = await totp_svc.get_state(SENTINEL_USER_ID)
    if not secret:
        raise HTTPException(400, "no pending TOTP secret — call /setup first")
    code = body.code.strip().replace(" ", "")
    if not pyotp.TOTP(secret).verify(code, valid_window=1):
        raise HTTPException(401, "invalid code")
    await totp_svc.enable(SENTINEL_USER_ID)
    return SessionInfo(authed=True, totp_enabled=True)


@router.post("/totp/disable", response_model=SessionInfo)
async def totp_disable(body: TotpVerifyRequest, _: bool = Depends(require_auth)) -> SessionInfo:
    """Disable TOTP. Must verify a current code so a stolen session can't disable."""
    if not await verify_totp(body.code):
        raise HTTPException(401, "invalid code")
    await totp_svc.disable(SENTINEL_USER_ID)
    return SessionInfo(authed=True, totp_enabled=False)


# ── Signup / email-verification / password-reset ────────────────────────────

@router.post("/signup")
async def signup(body: SignupRequest, request: Request) -> dict:
    await check_auth_rate(request, kind="signup")
    try:
        await signup_svc.signup(body.email, body.password)
    except ValueError as e:
        msg = str(e)
        if "disabled" in msg:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "signups disabled")
        raise HTTPException(status.HTTP_400_BAD_REQUEST, msg)
    # Always return neutral 200 (no enumeration about whether email was already taken)
    return {"ok": True, "message": "check your email to verify"}


@router.get("/verify-email")
async def verify_email(token: str) -> dict:
    ok = await signup_svc.verify_email(token)
    if not ok:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid or expired token")
    return {"ok": True}


@router.post("/forgot-password")
async def forgot_password(body: ForgotRequest, request: Request) -> dict:
    await check_auth_rate(request, kind="reset")
    await signup_svc.request_password_reset(body.email)
    # Always return 200 (no enumeration)
    return {"ok": True, "message": "if the email exists, a reset link has been sent"}


@router.post("/reset-password")
async def reset_password(body: ResetRequest) -> dict:
    ok = await signup_svc.complete_password_reset(body.token, body.new_password)
    if not ok:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid or expired token")
    return {"ok": True}
