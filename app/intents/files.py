"""File-storage intents — single entry point for both REST and MCP callers.

Today: thin pass-through to app.services.storage (file I/O) and
app.services.file_index (full-text search + re-indexing). The user_id
parameter is accepted but ignored until Phase 2 wires up per-user
namespacing.

All public functions in app.services.storage are async def; file_index
exposes two async def functions (index_all, search). No sync-to-async
promotion is needed.
"""
from typing import Any
from uuid import UUID

from ..services import file_index as file_index_svc
from ..services import storage as svc


async def list_files(
    user_id: UUID, prefix: str = "", *, limit: int = 200
) -> list[dict[str, Any]]:
    return await svc.list_files(prefix, limit=limit)


async def list_recursive(user_id: UUID, prefix: str) -> list[str]:
    return await svc.list_recursive(prefix)


async def download(user_id: UUID, path: str) -> bytes:
    return await svc.download(path)


async def exists(user_id: UUID, path: str) -> bool:
    return await svc.exists(path)


async def stat(user_id: UUID, path: str) -> dict[str, Any] | None:
    return await svc.stat(path)


async def upload(
    user_id: UUID,
    path: str,
    data: bytes,
    content_type: str = "application/octet-stream",
) -> dict[str, Any]:
    return await svc.upload(path, data, content_type)


async def delete(user_id: UUID, paths: list[str]) -> dict[str, Any]:
    return await svc.delete(paths)


async def signed_url(user_id: UUID, path: str, expires_in: int = 3600) -> str:
    return await svc.signed_url(path, expires_in)


async def signed_upload_url(user_id: UUID, path: str) -> dict[str, Any]:
    return await svc.signed_upload_url(path)


async def move(user_id: UUID, source: str, destination: str) -> dict[str, Any]:
    return await svc.move(source, destination)


async def search(user_id: UUID, q: str, limit: int = 20) -> list[dict[str, Any]]:
    return await file_index_svc.search(q, limit)


async def index_all(user_id: UUID) -> dict[str, Any]:
    return await file_index_svc.index_all()
