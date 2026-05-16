"""Course files browser API.

Browse, search, upload, move, and delete files under `STUDY_ROOT` (defaults
to `/opt/courses`). All routes are session-auth-gated.

  GET    /api/files/list?prefix=…      list entries (folders + files) at a prefix
  GET    /api/files/signed-url?path=…  same-origin URL the browser can fetch
  GET    /api/files/raw?path=…         stream a file from disk (cookie-auth)
  POST   /api/files/upload-url         mint a per-upload PUT target
  PUT    /api/files/upload-target?…    receive the body and persist it
  POST   /api/files/folder             create an empty folder (.keep marker)
  POST   /api/files/move               rename / move a file or folder
  DELETE /api/files                    delete a file or folder (recursive)
  GET    /api/files/lecture-materials  files grouped by `NN_lecture` prefix
  GET    /api/files/search             full-text search via the file_index
"""
from __future__ import annotations

import mimetypes
import os
import unicodedata
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse

from .. import db
from ..auth import require_user, User
from ..intents import files as intent


_UMLAUT_MAP = str.maketrans({
    "ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss",
    "Ä": "Ae", "Ö": "Oe", "Ü": "Ue",
})


def _sanitize_path(p: str) -> str:
    """Normalise a user-supplied storage path: ASCII-fold umlauts, drop
    diacritics via NFKD, collapse double slashes, and strip a leading
    slash. Keeps keys consistent across uploaders running on systems with
    different filename conventions."""
    s = p.translate(_UMLAUT_MAP)
    s = unicodedata.normalize("NFKD", s)
    s = s.encode("ascii", "ignore").decode("ascii")
    parts = [seg for seg in s.split("/") if seg]
    return "/".join(parts)


router = APIRouter(prefix="/files", tags=["files"], dependencies=[Depends(require_user)])


@router.get("/list")
async def list_files(prefix: str = Query(default=""), limit: int = Query(default=500, le=1000), user: User = Depends(require_user)) -> list[dict[str, Any]]:
    """List entries at the given prefix. Not recursive — drill down by passing
    a folder's path as the next prefix. Returns a sorted list of
    {name, path, type, size?, content_type?, updated_at?}."""
    clean = (prefix or "").strip().strip("/")
    entries = await intent.list_files(user.id, clean, limit=limit)
    out: list[dict[str, Any]] = []
    for e in entries:
        name = e.get("name") or ""
        if not name:
            continue
        path = f"{clean}/{name}" if clean else name
        if e.get("id") is None:
            out.append({"name": name, "path": path, "type": "folder"})
        else:
            meta = e.get("metadata") or {}
            out.append(
                {
                    "name": name,
                    "path": path,
                    "type": "file",
                    "size": meta.get("size"),
                    "content_type": meta.get("mimetype"),
                    "updated_at": e.get("updated_at"),
                }
            )
    # Folders first, then files — each alphabetised
    out.sort(key=lambda e: (0 if e["type"] == "folder" else 1, e["name"].lower()))
    return out


@router.get("/signed-url")
async def signed_url(path: str = Query(...), expires_in: int = Query(default=3600, ge=60, le=86400), user: User = Depends(require_user)) -> dict[str, Any]:
    """Mint a signed URL for the given object path. Default 1-hour expiry so
    the browser can cache the PDF response for reasonable repeat views."""
    if not path or ".." in path:
        raise HTTPException(400, "invalid path")
    try:
        url = await intent.signed_url(user.id, path, expires_in)
    except Exception as exc:
        raise HTTPException(404, f"not found: {exc}") from exc
    return {"url": url, "expires_in": expires_in}


@router.post("/upload-url")
async def upload_url(body: dict[str, Any] = Body(...), user: User = Depends(require_user)) -> dict[str, Any]:
    """Return a single-use URL the browser can PUT a file body to.

    Body: `{path: string}`. The path is sanitised server-side (umlaut-fold,
    NFKD, no `..`) so the key matches what other uploaders would produce.
    Two-step uploads keep large bodies off this JSON endpoint and let the
    actual write stream straight to disk via PUT /api/files/upload-target.
    """
    raw = (body.get("path") or "").strip().strip("/")
    if not raw or ".." in raw:
        raise HTTPException(400, "invalid path")
    key = _sanitize_path(raw)
    if not key:
        raise HTTPException(400, "path empty after sanitisation")
    try:
        result = await intent.signed_upload_url(user.id, key)
    except Exception as exc:
        raise HTTPException(500, f"failed to sign upload: {exc}") from exc
    return result


def _safe_key(raw: str) -> str:
    """Reject traversal, normalise slashes. Empty result raises."""
    cleaned = (raw or "").strip().strip("/")
    if not cleaned or ".." in cleaned:
        raise HTTPException(400, "invalid path")
    return cleaned


@router.delete("")
async def delete(
    path: str = Query(...),
    kind: str = Query(default="file", pattern="^(file|folder)$"),
    user: User = Depends(require_user),
) -> dict[str, Any]:
    """Delete a file (`kind=file`) or a folder and everything under it
    (`kind=folder`, recursive)."""
    key = _safe_key(path)
    if kind == "file":
        try:
            await intent.delete(user.id, [key])
        except Exception as exc:
            raise HTTPException(500, f"failed to delete: {exc}") from exc
        return {"deleted": [key]}

    try:
        children = await intent.list_recursive(user.id, key)
    except Exception as exc:
        raise HTTPException(500, f"failed to list folder: {exc}") from exc
    if not children:
        return {"deleted": []}
    try:
        await intent.delete(user.id, children)
    except Exception as exc:
        raise HTTPException(500, f"failed to delete folder: {exc}") from exc
    return {"deleted": children}


@router.post("/folder")
async def create_folder(body: dict[str, Any] = Body(...), user: User = Depends(require_user)) -> dict[str, Any]:
    """Create an empty folder by writing a `.keep` placeholder so the
    prefix appears in directory listings."""
    raw = (body.get("path") or "").strip().strip("/")
    if not raw or ".." in raw:
        raise HTTPException(400, "invalid path")
    key = _sanitize_path(raw)
    if not key:
        raise HTTPException(400, "path empty after sanitisation")
    placeholder = f"{key}/.keep"
    try:
        await intent.upload(user.id, placeholder, b"", content_type="application/octet-stream")
    except Exception as exc:
        raise HTTPException(500, f"failed to create folder: {exc}") from exc
    return {"folder": key, "placeholder": placeholder}


@router.post("/move")
async def move(body: dict[str, Any] = Body(...), user: User = Depends(require_user)) -> dict[str, Any]:
    """Rename or move a file or folder within `STUDY_ROOT`.

    Body: `{from, to, kind: "file"|"folder"}`. For files this is a single
    rename. For folders the move is fan-out: every descendant is relocated
    individually so subdirectories preserve relative structure.
    """
    src = _safe_key(body.get("from") or "")
    dst_raw = (body.get("to") or "").strip().strip("/")
    if not dst_raw or ".." in dst_raw:
        raise HTTPException(400, "invalid destination")
    dst = _sanitize_path(dst_raw)
    if not dst:
        raise HTTPException(400, "destination empty after sanitisation")
    kind = body.get("kind") or "file"
    if kind not in ("file", "folder"):
        raise HTTPException(400, "kind must be file or folder")
    if src == dst:
        return {"moved": []}
    if kind == "file":
        try:
            await intent.move(user.id, src, dst)
        except Exception as exc:
            raise HTTPException(500, f"failed to move: {exc}") from exc
        return {"moved": [{"from": src, "to": dst}]}

    # folder: list children, move each preserving relative path
    try:
        children = await intent.list_recursive(user.id, src)
    except Exception as exc:
        raise HTTPException(500, f"failed to list folder: {exc}") from exc
    moved: list[dict[str, str]] = []
    for child in children:
        rel = child[len(src) :].lstrip("/")
        new_path = f"{dst}/{rel}" if rel else dst
        try:
            await intent.move(user.id, child, new_path)
            moved.append({"from": child, "to": new_path})
        except Exception as exc:
            raise HTTPException(
                500, f"failed mid-move at {child}: {exc} ({len(moved)} moved so far)"
            ) from exc
    return {"moved": moved}


@router.get("/lecture-materials")
async def lecture_materials(course_code: str = Query(...), user: User = Depends(require_user)) -> dict[str, list[dict[str, Any]]]:
    """List Moodle files grouped by lecture number for a course.

    Walks the course folder and matches files of the form `<NN>_lecture*`,
    grouping by the leading number. Returns `{lecture_number: [{name, path, size}, …]}`.
    Lecture-less files (no NN prefix) end up under the empty string key.
    """
    row = await db.fetchrow(
        "SELECT folder_name FROM courses WHERE code = %s LIMIT 1",
        course_code.upper(),
    )
    if row is None:
        raise HTTPException(400, f"unknown course code {course_code!r}")
    folder = (row.get("folder_name") or "").strip() or course_code.upper()
    try:
        # list_recursive returns full keys under the prefix
        keys = await intent.list_recursive(user.id, folder)
    except Exception as exc:
        raise HTTPException(500, f"course tree list failed: {exc}") from exc

    import re
    pat = re.compile(r"^(\d{1,3})_lecture")
    grouped: dict[str, list[dict[str, Any]]] = {}
    for key in keys:
        # only top-level files (skip nested like Uebungsblaetter/, Loesungen/, data/)
        rel = key[len(folder) + 1 :] if key.startswith(folder + "/") else key
        if "/" in rel:
            continue
        m = pat.match(rel)
        bucket_key = str(int(m.group(1))) if m else ""
        grouped.setdefault(bucket_key, []).append({
            "name": rel,
            "path": key,
        })
    return grouped


@router.get("/search")
async def search(q: str = Query(..., min_length=2), limit: int = Query(20, le=100), user: User = Depends(require_user)) -> list[dict[str, Any]]:
    """Full-text search across indexed course-tree files.

    Returns ranked matches with snippets. Match terms are wrapped in
    `<<…>>` markers in the snippet so the frontend can highlight them.
    """
    return await intent.search(user.id, q, limit)


@router.get("/raw")
async def raw_file(path: str = Query(...), user: User = Depends(require_user)):
    """Stream a file from `STUDY_ROOT` to the browser.

    Same-origin URL: the session cookie authenticates the request. Used
    by the in-browser PDF preview, ipynb viewer, image embeds, etc.
    """
    if not path or ".." in path:
        raise HTTPException(400, "invalid path")
    meta = await intent.stat(user.id, path)
    if not meta:
        raise HTTPException(404, f"not found: {path}")
    # Resolve via the storage layer so the same per-user traversal guard
    # applies (path resolves under STUDY_ROOT/<user_id>/).
    from ..services import storage as storage_svc
    try:
        target = storage_svc._safe_resolve(user.id, path)
    except ValueError as exc:
        raise HTTPException(400, f"invalid path: {exc}") from exc
    return FileResponse(
        path=str(target),
        media_type=meta["mimetype"],
        filename=target.name,
        headers={
            "Cache-Control": "private, max-age=3600",
        },
    )


@router.put("/upload-target")
async def upload_target(request: Request, path: str = Query(...), user: User = Depends(require_user)) -> dict[str, Any]:
    """Receive a raw PUT body and write it to STUDY_ROOT/<path>.

    Pair with POST /upload-url which mints the URL pointing here. Same-origin,
    cookie-auth'd. Body is the file bytes. Path is sanitised the same way the
    laptop sync does it (umlauts → ascii, no traversal).
    """
    if not path or ".." in path:
        raise HTTPException(400, "invalid path")
    key = _sanitize_path(path)
    if not key:
        raise HTTPException(400, "path empty after sanitisation")
    body = await request.body()
    if not body:
        raise HTTPException(400, "empty body")
    content_type = request.headers.get("content-type") or "application/octet-stream"
    try:
        result = await intent.upload(user.id, key, body, content_type)
    except Exception as exc:
        raise HTTPException(500, f"upload failed: {exc}") from exc
    return result


@router.post("/sync-moodle")
async def sync_moodle(course: Optional[str] = Query(default=None)) -> dict[str, Any]:
    """Trigger an immediate Moodle scrape via the n8n webhook.

    Optional `course` filter: pass a course code or folder name to scrape
    only that one course (~2s instead of the full ~8s sync).
    """
    webhook_url = os.environ.get("N8N_MOODLE_WEBHOOK_URL", "").strip()
    if not webhook_url:
        raise HTTPException(
            503,
            "N8N_MOODLE_WEBHOOK_URL is not configured on this deployment.",
        )
    params = {"course": course} if course else None
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.get(webhook_url, params=params)
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"n8n webhook failed: {exc}") from exc
    except Exception as exc:
        raise HTTPException(500, f"unexpected error: {exc}") from exc
    written = data.get("applied", {}).get("written", []) or []
    plan = data.get("planSummary", {}) or {}
    return {
        "ok": bool(data.get("ok")),
        "written_count": len(written),
        "plan": plan,
        "errors": plan.get("errors", 0),
        "course": course,
    }
