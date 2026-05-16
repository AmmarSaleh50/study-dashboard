"""End-to-end integration tests for the routes that aggregate multiple
services. These exist specifically to catch the "forgot to await" class of
bug introduced when migrating callers to async — a missed await would
serialize as a coroutine repr and either 500 or fail a Pydantic shape
check, which is exactly what these tests assert against.

`/api/health` exercises `db.fetchval` + `storage_svc.list_files`.
`/api/dashboard` exercises every list_* service through `dashboard.py`.
"""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_health_returns_ok_with_db_and_storage(client, db_conn, tmp_path, monkeypatch):
    """Health check must report db=ok and storage=ok with no `coroutine` reprs."""
    monkeypatch.setenv("STUDY_ROOT", str(tmp_path))
    resp = await client.get("/api/health")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True, body
    assert body["db"] == "ok", body
    assert body["storage"].startswith("ok "), body


@pytest.mark.asyncio
async def test_dashboard_aggregates_every_service(db_conn, monkeypatch):
    """The dashboard route must return the full DashboardSummary shape with
    every list field present and Pydantic-valid — no awaited-but-uninvoked
    coroutines slipping into the response."""
    from httpx import ASGITransport, AsyncClient

    import app.db as db_module
    from app.auth import require_user, _sentinel_user
    from app.main import create_app

    monkeypatch.setattr(db_module, "_pool", db_conn)
    app = create_app()
    # Bypass the cookie-signed auth — Depends(require_user) is short-circuited
    # to always return the sentinel User for the duration of this test.
    app.dependency_overrides[require_user] = lambda: _sentinel_user()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/dashboard")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # Empty DB: every list is [], plus a `now` timestamp + an empty fall_behind.
    for key in (
        "courses", "slots", "exams", "deliverables",
        "tasks", "study_topics", "lectures", "fall_behind",
    ):
        assert isinstance(body.get(key), list), (key, body.get(key))
    assert "now" in body and isinstance(body["now"], str)


@pytest.mark.asyncio
async def test_login_flow_uses_async_db_paths(client, db_conn, monkeypatch):
    """Drive /auth/login through the async ratelimit + auth.get_totp_state
    paths. Expects a 401 (no password configured, but the request must reach
    that error rather than 500-ing on a missed await)."""
    # No app_password_hash configured → verify_password returns False → 401.
    resp = await client.post("/api/auth/login", json={"password": "irrelevant"})
    assert resp.status_code == 401, resp.text
    assert resp.json()["detail"] == "invalid password"
