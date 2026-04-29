"""HTTP Streamable transport for the OpenStudy MCP server.

Mounted under `/mcp` in app/main.py. Reuses app.mcp_tools.register_tools
to wire every tool onto the FastMCP instance.

Auth: Bearer access tokens issued by our OAuth AS (app/services/oauth.py).

Note on lifespan: some serverless runtimes do NOT invoke ASGI
lifespan events reliably, so FastMCP's StreamableHTTPSessionManager never
gets its task group started via the normal path. `_per_request_mcp_app`
below sidesteps this by rebuilding the FastMCP server + entering its
lifespan context fresh on every inbound request. Heavy compared to a
long-lived session manager, but bulletproof.
"""
from __future__ import annotations

import logging
from typing import Optional

from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from .config import get_settings
from .mcp_tools import register_tools
from .services import oauth as oauth_svc

log = logging.getLogger(__name__)


class PostgrestTokenVerifier(TokenVerifier):
    def __init__(self, resource: str):
        self._resource = resource

    async def verify_token(self, token: str) -> Optional[AccessToken]:
        row = oauth_svc.verify_access_token(token)
        if not row:
            return None
        scope = row.get("scope") or "mcp"
        return AccessToken(
            token=token,
            client_id=row["client_id"],
            scopes=scope.split(),
            expires_at=None,
            resource=self._resource,
        )


def _public_origin() -> str:
    s = get_settings()
    if s.public_url:
        return s.public_url.rstrip("/")
    return "http://localhost:8000"


_SERVER_INSTRUCTIONS = """\
OpenStudy — personal study dashboard. Tracks a student's courses and everything attached \
to them: weekly schedule slots, individual lecture sessions, atomic study \
topics, graded deliverables, end-of-semester exams, personal tasks, and an \
activity log.

── Mental model ────────────────────────────────────────────────────────────
A course has a `code` (short uppercase id like ASB / CS101). Every other \
entity is keyed off that code. Four easy-to-confuse entity families:

  • schedule_slot = the weekly recurring timetable entry ("Mon 10:00 lecture")
  • lecture       = one concrete held session on a specific date
  • study_topic   = the smallest chunk of material the user tracks progress on
  • deliverable   = a graded submission (problem set, project, lab, etc.)

Plus: task (personal todo, not graded), exam (one per course, end-of-semester),
event (activity log entry).

── How to orient yourself ──────────────────────────────────────────────────
1. Call `get_app_settings` first — gives you the user's timezone, locale, \
   semester window, display name. Required for correct date math.
2. Call `get_dashboard` to see everything at once. Prefer this over 5+ \
   separate `list_*` calls when you need broad context.
3. For a single course, call `get_course(code)` + the relevant `list_*` with \
   `course_code=code`.

── Conventions ─────────────────────────────────────────────────────────────
• Kind enums are English-canonical:
    slot/lecture.kind  = lecture | exercise | tutorial | lab
    study_topic.kind   = lecture | exercise | reading
    deliverable.kind   = submission | project | lab | block
  Legacy German values (Vorlesung, Übung, Tutorium, Praktikum, abgabe, …) are \
  still accepted on input and normalised to English — but emit English.
• Dates are ISO: `YYYY-MM-DD` for dates, full ISO-8601 with timezone for \
  datetimes. Use `now_here` when you need "now" in the user's timezone.
• Ask before destructive operations (`delete_*`). They cascade.

── Shortcut tools vs patches ───────────────────────────────────────────────
Prefer the named shortcut over `update_*` when one exists — it's less \
error-prone: `mark_studied`, `complete_task`, `mark_deliverable_submitted`, \
`mark_lecture_attended`, `reopen_task`, `reopen_deliverable`, \
`set_confidence`.

── What to escalate to the user ────────────────────────────────────────────
• Ambiguity between similar entities (e.g. "log the ASB lecture" — did they \
  mean create a `lecture` row, add `study_topics`, or record an `event`?).
• Any destructive action.
• Unknown `course_code` values — `list_courses` first, then confirm.
"""


def _build_server() -> FastMCP:
    origin = _public_origin()
    # Resource URL stays slash-less because the well-known metadata route
    # (.well-known/oauth-protected-resource/<resource-path>) is registered
    # by the framework without a trailing slash; advertising `/mcp/` here
    # would point clients at a 307 redirect and the bearer header gets
    # dropped on the redirect by some clients. The reverse proxy handles
    # `/mcp` → `/mcp/` rewrites for actual JSON-RPC traffic.
    resource_url = f"{origin}/mcp"
    server = FastMCP(
        "openstudy",
        instructions=_SERVER_INSTRUCTIONS,
        token_verifier=PostgrestTokenVerifier(resource_url),
        auth=AuthSettings(
            issuer_url=origin,
            resource_server_url=resource_url,
        ),
        # FastMCP's default host (127.0.0.1) auto-enables DNS-rebinding protection
        # locked to localhost, which 421s any public-domain request. Disable it —
        # Bearer-token auth is the real gate here, not Host validation.
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=False,
        ),
        streamable_http_path="/",
        stateless_http=True,
    )
    register_tools(server)
    return server


async def _per_request_mcp_app(scope, receive, send) -> None:
    """Per-request FastMCP build. Some serverless runtimes don't
    invoke ASGI lifespan AND each invocation may reset async state, so the
    only reliable pattern is to rebuild the server + session manager for
    every request. Heavy but bulletproof.
    """
    if scope["type"] == "lifespan":
        msg = await receive()
        if msg["type"] == "lifespan.startup":
            await send({"type": "lifespan.startup.complete"})
            msg = await receive()
        if msg["type"] == "lifespan.shutdown":
            await send({"type": "lifespan.shutdown.complete"})
        return
    try:
        server = _build_server()
        inner = server.streamable_http_app()
        async with inner.router.lifespan_context(inner):
            await inner(scope, receive, send)
    except Exception:
        # Log server-side, never echo the traceback to the client (it can
        # leak internal paths, DSN fragments, env values that wound up in
        # error messages, etc.).
        log.exception("MCP handler error (per-request)")
        body = b"MCP handler error. Server-side details have been logged."
        try:
            await send(
                {
                    "type": "http.response.start",
                    "status": 500,
                    "headers": [(b"content-type", b"text/plain; charset=utf-8")],
                }
            )
            await send({"type": "http.response.body", "body": body})
        except Exception:
            pass  # response already started; nothing to do


def build_mcp_http_app():
    return _per_request_mcp_app
