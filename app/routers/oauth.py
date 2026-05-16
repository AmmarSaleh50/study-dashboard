"""OAuth 2.1 authorization server + resource server discovery.

Implements the minimum spec for Claude.ai's custom remote MCP connectors:
  - RFC 9728 `/.well-known/oauth-protected-resource`
  - RFC 8414 `/.well-known/oauth-authorization-server`
  - RFC 7591 Dynamic Client Registration
  - Authorization Code grant with PKCE-S256 (OAuth 2.1 required)

Consent reuses the existing dashboard password session — user logs in once,
approves Claude.ai once, done.
"""
from __future__ import annotations

import html
from typing import Any, Optional
from urllib.parse import quote, urlencode

from fastapi import APIRouter, Body, Cookie, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from ..auth import COOKIE_NAME, optional_auth, require_user, User
from ..config import get_settings
from ..services import oauth as oauth_svc


router = APIRouter(tags=["oauth"])


def _origin(request: Request) -> str:
    s = get_settings()
    if s.public_url:
        return s.public_url.rstrip("/")
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.url.netloc
    return f"{proto}://{host}"


def _safe_redirect_uri(uri: str) -> str:
    """Reject `javascript:` / `data:` / `vbscript:` redirect URIs. Returns
    the URI unchanged if safe, an empty string if not. Empty string is
    treated as 'no Deny link' downstream.

    OAuth 2.1 already requires `redirect_uri` to be pre-registered, so this
    is defence in depth — Dynamic Client Registration (`/oauth/register`)
    currently has no allow-list filter, and a misconfigured client could
    still wind up here.
    """
    lowered = uri.strip().lower()
    for bad in ("javascript:", "data:", "vbscript:", "file:"):
        if lowered.startswith(bad):
            return ""
    return uri


# ─────────────────────── Discovery metadata ───────────────────────

@router.get("/.well-known/oauth-protected-resource", include_in_schema=False)
@router.get("/.well-known/oauth-protected-resource/mcp", include_in_schema=False)
async def oauth_protected_resource(request: Request) -> JSONResponse:
    """RFC 9728 — tells clients where to find the authorization server."""
    origin = _origin(request)
    return JSONResponse(
        {
            "resource": f"{origin}/mcp",
            "authorization_servers": [origin],
            "bearer_methods_supported": ["header"],
            "scopes_supported": ["mcp"],
        }
    )


@router.get("/.well-known/oauth-authorization-server", include_in_schema=False)
async def oauth_authorization_server(request: Request) -> JSONResponse:
    """RFC 8414 — advertises the AS endpoints."""
    origin = _origin(request)
    return JSONResponse(
        {
            "issuer": origin,
            "authorization_endpoint": f"{origin}/oauth/authorize",
            "token_endpoint": f"{origin}/oauth/token",
            "registration_endpoint": f"{origin}/oauth/register",
            "revocation_endpoint": f"{origin}/oauth/revoke",
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code"],
            "code_challenge_methods_supported": ["S256"],
            "token_endpoint_auth_methods_supported": ["none"],
            "revocation_endpoint_auth_methods_supported": ["none"],
            "scopes_supported": ["mcp"],
        }
    )


# ─────────────────────── Dynamic Client Registration (RFC 7591) ───────────────────────

@router.post("/oauth/register", include_in_schema=False)
async def register_client(body: dict[str, Any] = Body(...)) -> JSONResponse:
    redirect_uris = body.get("redirect_uris") or []
    if not redirect_uris or not isinstance(redirect_uris, list):
        raise HTTPException(400, "redirect_uris required")
    client = await oauth_svc.create_client(
        client_name=body.get("client_name") or "Unnamed client",
        redirect_uris=redirect_uris,
        token_endpoint_auth_method="none",
        public=True,
    )
    return JSONResponse(
        status_code=201,
        content={
            "client_id": client["client_id"],
            "client_name": client["client_name"],
            "redirect_uris": client["redirect_uris"],
            "token_endpoint_auth_method": "none",
            "grant_types": ["authorization_code"],
            "response_types": ["code"],
        },
    )


# ─────────────────────── Authorization + consent ───────────────────────

@router.get("/oauth/authorize", include_in_schema=False)
async def authorize(
    request: Request,
    response_type: str = Query(...),
    client_id: str = Query(...),
    redirect_uri: str = Query(...),
    code_challenge: str = Query(...),
    code_challenge_method: str = Query("S256"),
    scope: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    study_session: Optional[str] = Cookie(default=None, alias=COOKIE_NAME),
) -> Response:
    if response_type != "code":
        raise HTTPException(400, "unsupported response_type")
    if code_challenge_method != "S256":
        raise HTTPException(400, "unsupported code_challenge_method (S256 only)")

    client = await oauth_svc.get_client(client_id)
    if not client:
        raise HTTPException(400, "unknown client_id")
    if redirect_uri not in client["redirect_uris"]:
        raise HTTPException(400, "redirect_uri not registered for client")

    authed = await optional_auth(study_session)
    if not authed:
        params = {
            "response_type": response_type,
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "code_challenge": code_challenge,
            "code_challenge_method": code_challenge_method,
        }
        if scope:
            params["scope"] = scope
        if state:
            params["state"] = state
        back = f"/oauth/authorize?{urlencode(params)}"
        return RedirectResponse(f"/login?next={quote(back, safe='')}")

    # Escape every interpolated value. quote=True covers " and ' so an
    # attacker can't break out of an attribute value. _safe_redirect_uri
    # additionally rejects scheme injection on the Deny link.
    safe_name = html.escape(client["client_name"] or "a client", quote=True)
    safe_client_id = html.escape(client_id, quote=True)
    safe_redirect = _safe_redirect_uri(redirect_uri)
    safe_redirect_attr = html.escape(safe_redirect, quote=True)
    safe_challenge = html.escape(code_challenge, quote=True)
    safe_method = html.escape(code_challenge_method or "S256", quote=True)
    safe_scope = html.escape(scope or "", quote=True)
    safe_state = html.escape(state or "", quote=True)
    # Deny link goes back to redirect_uri ONLY if it's a safe scheme;
    # otherwise we strip the link to avoid producing a clickable
    # javascript:/data: URI in the rendered page.
    deny_href = (
        f"{safe_redirect}?error=access_denied&state={state or ''}"
        if safe_redirect
        else "#"
    )
    deny_href_attr = html.escape(deny_href, quote=True)

    page = f"""<!doctype html>
<html lang="en" class="dark"><head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Authorize {safe_name}</title>
  <style>
    html, body {{ margin: 0; padding: 0; background: #0f0f11; color: #fafafa; font-family: -apple-system, system-ui, "Segoe UI", sans-serif; }}
    body {{ min-height: 100vh; display: flex; align-items: center; justify-content: center; padding: 1.25rem; }}
    .card {{ background: #181a1c; border: 1px solid #2a2d31; border-radius: 14px; padding: 1.75rem 1.75rem 1.5rem; width: 100%; max-width: 440px; box-shadow: 0 20px 60px rgba(0,0,0,0.5); }}
    h1 {{ margin: 0 0 0.25rem; font-size: 1.25rem; font-weight: 600; letter-spacing: -0.01em; }}
    p {{ color: #a8acb3; font-size: 0.9rem; line-height: 1.5; margin: 0.75rem 0 0; }}
    .name {{ color: #fafafa; font-weight: 600; }}
    ul {{ color: #a8acb3; font-size: 0.85rem; padding-left: 1.2rem; margin: 0.75rem 0 0; line-height: 1.6; }}
    .actions {{ display: flex; gap: 0.5rem; margin-top: 1.75rem; }}
    button, a.btn {{ flex: 1; padding: 0.7rem 1rem; border-radius: 8px; border: 1px solid #2a2d31; font-size: 0.9rem; font-weight: 500; cursor: pointer; text-align: center; text-decoration: none; color: #fafafa; background: transparent; font-family: inherit; }}
    button.primary {{ background: #fafafa; color: #0f0f11; border-color: #fafafa; }}
    button.primary:hover {{ background: #e5e5e5; }}
    a.btn.ghost {{ color: #a8acb3; }}
    a.btn.ghost:hover {{ color: #fafafa; background: #232629; }}
  </style>
</head>
<body>
  <div class="card">
    <h1>Authorize access</h1>
    <p><span class="name">{safe_name}</span> is asking to access your OpenStudy session on your behalf.</p>
    <p>Approving will allow it to:</p>
    <ul>
      <li>Read your courses, tasks, deliverables, lectures, and study topics</li>
      <li>Create, update, and delete those same resources</li>
      <li>Record activity events</li>
    </ul>
    <form method="post" action="/oauth/consent" class="actions">
      <input type="hidden" name="client_id" value="{safe_client_id}">
      <input type="hidden" name="redirect_uri" value="{safe_redirect_attr}">
      <input type="hidden" name="code_challenge" value="{safe_challenge}">
      <input type="hidden" name="code_challenge_method" value="{safe_method}">
      <input type="hidden" name="scope" value="{safe_scope}">
      <input type="hidden" name="state" value="{safe_state}">
      <a class="btn ghost" href="{deny_href_attr}">Deny</a>
      <button type="submit" class="primary">Approve</button>
    </form>
  </div>
</body></html>"""
    return HTMLResponse(content=page)


@router.post("/oauth/consent", include_in_schema=False)
async def consent(
    client_id: str = Form(...),
    redirect_uri: str = Form(...),
    code_challenge: str = Form(...),
    code_challenge_method: str = Form("S256"),
    scope: Optional[str] = Form(None),
    state: Optional[str] = Form(None),
    user: User = Depends(require_user),
) -> Response:

    client = await oauth_svc.get_client(client_id)
    if not client or redirect_uri not in client["redirect_uris"]:
        raise HTTPException(400, "invalid client/redirect")

    code = await oauth_svc.create_auth_code(
        client_id=client_id,
        redirect_uri=redirect_uri,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
        scope=scope or None,
    )
    params: dict[str, str] = {"code": code}
    if state:
        params["state"] = state
    return RedirectResponse(f"{redirect_uri}?{urlencode(params)}", status_code=302)


# ─────────────────────── Token revocation (RFC 7009) ───────────────────────

@router.post("/oauth/revoke", include_in_schema=False)
async def revoke(
    token: str = Form(...),
    token_type_hint: Optional[str] = Form(None),
    client_id: Optional[str] = Form(None),
) -> Response:
    """RFC 7009 token revocation. Public clients (auth_method=none) call this
    on logout. Per spec, the response is always 200 even when the token is
    unknown — surfacing a distinction would let callers enumerate live tokens."""
    await oauth_svc.revoke_token(token)
    return Response(status_code=200)


# ─────────────────────── Token endpoint ───────────────────────

@router.post("/oauth/token", include_in_schema=False)
async def token(
    grant_type: str = Form(...),
    code: str = Form(...),
    redirect_uri: str = Form(...),
    client_id: str = Form(...),
    code_verifier: str = Form(...),
) -> JSONResponse:
    if grant_type != "authorization_code":
        raise HTTPException(400, "unsupported_grant_type")
    row = await oauth_svc.consume_auth_code(code, client_id, redirect_uri, code_verifier)
    if not row:
        raise HTTPException(400, "invalid_grant")
    access_token, expires_in = await oauth_svc.create_access_token(client_id, row.get("scope"))
    return JSONResponse(
        {
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": expires_in,
            "scope": row.get("scope") or "mcp",
        }
    )
