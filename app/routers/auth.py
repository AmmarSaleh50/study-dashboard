import pyotp
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from ..services import totp as totp_svc
from ..services import auth_signup as signup_svc
from ..auth import (
    SENTINEL_USER_ID,
    clear_session,
    is_totp_required,
    issue_session,
    optional_auth,
    require_auth,
    verify_password,
    verify_totp,
)
from ..ratelimit import check_login_rate, record_login_attempt, check_auth_rate
from ..schemas import LoginRequest, SessionInfo, TotpSetupResponse, TotpVerifyRequest, SignupRequest, ForgotRequest, ResetRequest

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=SessionInfo)
async def login(body: LoginRequest, request: Request, response: Response) -> SessionInfo:
    await check_login_rate(request)
    ok = verify_password(body.password)
    # If password is correct AND TOTP is enabled, also require a valid code.
    # Frontend reads the 401 detail string to know whether to show the TOTP field.
    if ok and await is_totp_required():
        if not body.totp_code:
            # Don't record as a failed attempt — the password was correct,
            # the user is just at the start of the two-factor flow. Marking
            # this as a failure would eat the rate-limit budget on every
            # legitimate login.
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="totp_required")
        if not await verify_totp(body.totp_code):
            await record_login_attempt(request, False)
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid totp code")
    await record_login_attempt(request, ok)
    if not ok:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid password")
    issue_session(response, SENTINEL_USER_ID)
    return SessionInfo(authed=True, totp_enabled=await is_totp_required())


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
