"""Filesystem-backed storage layer.

Course materials live as plain files under `STUDY_ROOT` (defaults to
`/opt/courses`). All read/write/list/move/delete operations in the app
funnel through this module.

`list_files` returns `{name, id, updated_at, metadata: {size, mimetype}}`
per entry, with `id=None` marking folders so the UI can distinguish them
without a second stat.

Every operation emits an `events` row so the Activity page shows
everything that touches the course tree (MCP tool calls, web uploads,
periodic syncs).

All public functions are `async def`. Filesystem I/O is offloaded via
`asyncio.to_thread()` so we don't block the event loop on disk reads
or writes; `_log()` writes to Postgres through the async pool.
"""
from __future__ import annotations

import asyncio
import json
import logging
import mimetypes
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

from .. import db

log = logging.getLogger(__name__)


def _root() -> Path:
    return Path(os.environ.get("STUDY_ROOT", "/opt/courses"))


def _safe_resolve(rel: str) -> Path:
    """Join `rel` under STUDY_ROOT, refusing escape via `..` or absolute path.
    Returns the absolute path. Raises ValueError on traversal attempt."""
    root = _root().resolve()
    rel = (rel or "").lstrip("/")
    target = (root / rel).resolve()
    if root != target and root not in target.parents:
        raise ValueError(f"path escapes STUDY_ROOT: {rel!r}")
    return target


def _course_code_from_path(p: str | None) -> str | None:
    """Extract the leading path segment as a course code if it looks like one.
    Convention: paths under STUDY_ROOT are `<COURSE_CODE>/...` where
    COURSE_CODE is uppercase letters/digits/dashes. Returns None if the path
    doesn't match (e.g. empty list-prefix, or a top-level file)."""
    if not p:
        return None
    first = p.lstrip("/").split("/", 1)[0]
    # Match the convention: 2-12 chars, uppercase letters/digits/dash.
    # Don't be too lax — we'd rather log course_code=NULL than a bogus value.
    if 2 <= len(first) <= 12 and first == first.upper() and all(
        c.isalnum() or c == "-" for c in first
    ):
        return first
    return None


async def _log(kind: str, payload: dict[str, Any]) -> None:
    """Best-effort event log. Never breaks a storage op when the DB is
    having a moment — exceptions are swallowed.

    Extracts course_code from the payload's first path-shaped value (path,
    prefix, source, or first of paths[]). The events table has a
    course_code column that's been silently NULL for every storage event
    since v0.5.0 — fixed in Batch A so the activity log can filter by
    course."""
    # Find the first path-shaped value in the payload to derive course_code.
    candidate: str | None = None
    for key in ("path", "prefix", "source", "destination", "from", "to"):
        if key in payload and isinstance(payload[key], str):
            candidate = payload[key]
            break
    if candidate is None and isinstance(payload.get("paths"), list) and payload["paths"]:
        first_path = payload["paths"][0]
        if isinstance(first_path, str):
            candidate = first_path
    course_code = _course_code_from_path(candidate)

    payload_json = json.dumps(payload)
    try:
        if course_code:
            await db.execute(
                "INSERT INTO events (kind, course_code, payload) "
                "VALUES (%s, %s, %s::jsonb)",
                kind, course_code, payload_json,
            )
        else:
            await db.execute(
                "INSERT INTO events (kind, payload) VALUES (%s, %s::jsonb)",
                kind, payload_json,
            )
    except Exception:
        pass


def _mtime_iso(p: Path) -> str:
    return datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc).isoformat()


# ── sync helpers ─────────────────────────────────────────────────────────────
# Internal blocking implementations. The async public functions wrap these
# in `asyncio.to_thread()` so the event loop stays free for other work.


def _list_files_sync(prefix: str, limit: int) -> list[dict[str, Any]]:
    try:
        base = _safe_resolve(prefix)
    except ValueError:
        return []
    if not base.exists() or not base.is_dir():
        return []

    out: list[dict[str, Any]] = []
    try:
        entries = sorted(
            (p for p in base.iterdir() if not p.name.startswith(".")),
            key=lambda p: p.name.lower(),
        )
    except OSError:
        return []

    for child in entries[:limit]:
        if child.is_dir():
            out.append({
                "name": child.name,
                "id": None,
                "updated_at": _mtime_iso(child),
                "metadata": None,
            })
        else:
            mime, _ = mimetypes.guess_type(child.name)
            out.append({
                "name": child.name,
                "id": str(child.stat().st_ino),
                "updated_at": _mtime_iso(child),
                "metadata": {
                    "size": child.stat().st_size,
                    "mimetype": mime or "application/octet-stream",
                },
            })
    return out


def _list_recursive_sync(prefix: str) -> list[str]:
    try:
        base = _safe_resolve(prefix)
    except ValueError:
        return []
    if not base.exists() or not base.is_dir():
        return []
    root = _root().resolve()
    out: list[str] = []
    for p in base.rglob("*"):
        if p.is_file() and not any(part.startswith(".") for part in p.relative_to(root).parts):
            out.append(str(p.relative_to(root)).replace(os.sep, "/"))
    out.sort()
    return out


def _download_sync(path: str) -> bytes:
    target = _safe_resolve(path)
    if not target.is_file():
        raise FileNotFoundError(f"not found: {path}")
    return target.read_bytes()


def _exists_sync(path: str) -> bool:
    try:
        return _safe_resolve(path).is_file()
    except ValueError:
        return False


def _stat_sync(path: str) -> dict[str, Any] | None:
    try:
        target = _safe_resolve(path)
    except ValueError:
        return None
    if not target.is_file():
        return None
    mime, _ = mimetypes.guess_type(target.name)
    return {
        "path": path,
        "size": target.stat().st_size,
        "mimetype": mime or "application/octet-stream",
        "updated_at": _mtime_iso(target),
    }


def _upload_sync(path: str, data: bytes) -> None:
    target = _safe_resolve(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + f".tmp-{os.getpid()}")
    try:
        tmp.write_bytes(data)
        os.replace(tmp, target)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def _delete_sync(paths: list[str]) -> list[str]:
    deleted: list[str] = []
    for p in paths:
        try:
            target = _safe_resolve(p)
        except ValueError:
            continue
        if target.is_file():
            try:
                target.unlink()
                deleted.append(p)
            except OSError as e:
                log.warning("delete failed for %s: %s", p, e)
        elif target.is_dir():
            # safety: only allow rmtree on empty dirs here; recursive deletes
            # come through delete folder via the router which lists first.
            try:
                target.rmdir()
                deleted.append(p)
            except OSError:
                pass
    return deleted


def _move_sync(source: str, destination: str) -> None:
    src = _safe_resolve(source)
    dst = _safe_resolve(destination)
    if not src.exists():
        raise FileNotFoundError(f"source not found: {source}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))


# ── Read ─────────────────────────────────────────────────────────────────────


async def list_files(prefix: str = "", *, limit: int = 200) -> list[dict[str, Any]]:
    """List entries (folders + files) at the given prefix. Non-recursive.

    Each entry: `{name, id, updated_at, metadata: {size, mimetype}}`.
    Folders are returned with `id=None` and `metadata=None` so the caller
    can distinguish them from files without an extra stat call. Dotfiles
    (anything starting with `.`) are filtered out of listings.
    """
    out = await asyncio.to_thread(_list_files_sync, prefix, limit)
    await _log("storage:list", {"prefix": prefix, "count": len(out)})
    return out


async def list_recursive(prefix: str) -> list[str]:
    """Return every file path (relative to STUDY_ROOT) under `prefix`,
    descending into subfolders. Skips dotfiles."""
    return await asyncio.to_thread(_list_recursive_sync, prefix)


async def download(path: str) -> bytes:
    """Return raw bytes of a file."""
    data = await asyncio.to_thread(_download_sync, path)
    await _log("storage:read", {"path": path, "size": len(data)})
    return data


async def exists(path: str) -> bool:
    return await asyncio.to_thread(_exists_sync, path)


async def stat(path: str) -> dict[str, Any] | None:
    """Return file metadata or None if the path doesn't exist."""
    return await asyncio.to_thread(_stat_sync, path)


# ── Write ────────────────────────────────────────────────────────────────────


async def upload(path: str, data: bytes, content_type: str = "application/octet-stream") -> dict[str, Any]:
    """Write (or overwrite) a file. Atomic via tmp+rename within the same dir."""
    await asyncio.to_thread(_upload_sync, path, data)
    await _log("storage:upload", {"path": path, "size": len(data), "content_type": content_type})
    return {"path": path, "size": len(data), "content_type": content_type}


async def delete(paths: list[str]) -> dict[str, Any]:
    """Delete one or more files. Missing paths are silently OK (idempotent)."""
    deleted = await asyncio.to_thread(_delete_sync, paths)
    await _log("storage:delete", {"paths": paths, "count": len(deleted)})
    return {"deleted": deleted}


async def signed_url(path: str, expires_in: int = 3600) -> str:
    """Return an in-app URL the browser can fetch the file from.

    Same-origin path that hits `GET /api/files/raw`, which streams the
    file under session-cookie auth. The `expires_in` parameter is part
    of the API surface for parity with externally signed URLs but isn't
    enforced here — the session cookie is the auth token.
    """
    if not await exists(path):
        raise FileNotFoundError(f"not found: {path}")
    await _log("storage:sign", {"path": path, "expires_in": expires_in})
    return f"/api/files/raw?path={quote(path, safe='/')}"


async def signed_upload_url(path: str) -> dict[str, Any]:
    """Return a URL the browser can PUT the file body to.

    Two-step uploads: the JSON endpoint at `POST /api/files/upload-url`
    calls this to mint the target URL; the browser then PUTs the body
    there, which lands in `/api/files/upload-target` and persists it
    via `upload()`.
    """
    await _log("storage:sign:upload", {"path": path})
    return {
        "url": f"/api/files/upload-target?path={quote(path, safe='/')}",
        "token": None,
        "path": path,
    }


async def move(source: str, destination: str) -> dict[str, Any]:
    """Rename or move a file. Cross-directory moves work as long as both
    sides are under STUDY_ROOT."""
    await asyncio.to_thread(_move_sync, source, destination)
    await _log("storage:move", {"from": source, "to": destination})
    return {"from": source, "to": destination}
