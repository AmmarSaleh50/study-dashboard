"""OAuth 2.1 authorization server storage helpers (Postgres-backed).

Phase 0 (single-operator) deployment: the operator (server admin) authenticates
via the existing dashboard password cookie during the consent step. Users as a
distinct database concept are introduced in Phase 1 — until then every issued
token implicitly belongs to the operator.
"""
from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

from .. import db


AUTH_CODE_TTL_SEC = 600  # 10 min
ACCESS_TOKEN_TTL_SEC = 90 * 24 * 60 * 60  # 90 days


def _gen(n: int = 32) -> str:
    return secrets.token_urlsafe(n)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ─────────────────────── Clients ───────────────────────

async def create_client(
    *,
    client_name: str,
    redirect_uris: list[str],
    token_endpoint_auth_method: str = "none",
    public: bool = True,
) -> dict[str, Any]:
    client_id = _gen(16)
    client_secret = None if public else _gen(32)
    row = await db.fetchrow(
        "INSERT INTO oauth_clients "
        "(client_id, client_secret, client_name, redirect_uris, "
        " token_endpoint_auth_method) "
        "VALUES (%s, %s, %s, %s, %s) RETURNING *",
        client_id, client_secret, client_name, redirect_uris,
        token_endpoint_auth_method,
    )
    if row is None:
        raise ValueError(f"failed to register client '{client_name}'")
    return row


async def get_client(client_id: str) -> Optional[dict[str, Any]]:
    return await db.fetchrow(
        "SELECT * FROM oauth_clients WHERE client_id = %s LIMIT 1",
        client_id,
    )


# ─────────────────────── Auth codes ───────────────────────

async def create_auth_code(
    *,
    user_id: UUID,
    client_id: str,
    redirect_uri: str,
    code_challenge: str,
    code_challenge_method: str,
    scope: Optional[str],
) -> str:
    code = _gen(32)
    expires_at = _now() + timedelta(seconds=AUTH_CODE_TTL_SEC)
    await db.execute(
        "INSERT INTO oauth_auth_codes "
        "(user_id, code, client_id, redirect_uri, code_challenge, "
        " code_challenge_method, scope, expires_at) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
        user_id, code, client_id, redirect_uri, code_challenge,
        code_challenge_method, scope, expires_at,
    )
    return code


async def consume_auth_code(
    code: str, client_id: str, redirect_uri: str, code_verifier: str
) -> Optional[dict[str, Any]]:
    """Validate + invalidate the auth code in one shot. Returns the row on
    success, else None.

    Atomicity matters: a single `DELETE … RETURNING *` removes the row from
    the table at the same instant we read it, so two parallel callers can
    never both succeed with the same code (the second one's DELETE matches
    zero rows). This is stricter than the previous SELECT-then-UPDATE form
    which had a TOCTOU window.

    Validation order:
      1. DELETE the row if it exists AND has not expired (single SQL stmt).
      2. Then verify client_id / redirect_uri / PKCE challenge in Python.
    If any post-DELETE check fails the code is gone anyway — that's
    deliberate, the row is treated as burnt the moment it's looked up.
    """
    row = await db.fetchrow(
        "DELETE FROM oauth_auth_codes "
        "WHERE code = %s AND expires_at > now() "
        "RETURNING *",
        code,
    )
    if row is None:
        return None
    if row["client_id"] != client_id or row["redirect_uri"] != redirect_uri:
        return None

    # OAuth 2.1 mandates S256 — `plain` is rejected even if a code row
    # somehow ended up stored with method='plain' (the /authorize handler
    # already blocks it, but a direct POST to /oauth/consent skipped that
    # check until this guard was added).
    if row["code_challenge_method"] != "S256":
        return None
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    computed = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    if computed != row["code_challenge"]:
        return None

    return row


# ─────────────────────── Access tokens ───────────────────────

async def create_access_token(user_id: UUID, client_id: str, scope: Optional[str]) -> tuple[str, int]:
    token = _gen(48)
    expires_at = _now() + timedelta(seconds=ACCESS_TOKEN_TTL_SEC)
    await db.execute(
        "INSERT INTO oauth_tokens "
        "(user_id, token, client_id, scope, expires_at) VALUES (%s, %s, %s, %s, %s)",
        user_id, token, client_id, scope, expires_at,
    )
    return token, ACCESS_TOKEN_TTL_SEC


async def verify_access_token(token: str) -> Optional[dict[str, Any]]:
    """Return the token row if it's known, not revoked, and not expired."""
    row = await db.fetchrow(
        "SELECT * FROM oauth_tokens "
        "WHERE token = %s AND revoked = false "
        "  AND (expires_at IS NULL OR expires_at > now()) "
        "LIMIT 1",
        token,
    )
    return row


async def revoke_token(token: str) -> None:
    """Mark an access token as revoked. After this, verify_access_token
    returns None for the token. No-op if the token doesn't exist."""
    await db.execute(
        "UPDATE oauth_tokens SET revoked = true WHERE token = %s",
        token,
    )


__all__ = [
    "create_client",
    "get_client",
    "create_auth_code",
    "consume_auth_code",
    "create_access_token",
    "verify_access_token",
    "revoke_token",
]
