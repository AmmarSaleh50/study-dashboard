"""File-storage intents — single entry point for both REST and MCP callers.

Per-user pass-through: every storage call forwards user_id to the service
so paths resolve under `STUDY_ROOT/<user_id>/...`. Search filters file_index
rows by user_id. `index_all` is operator-scoped (walks every user's tree);
the user_id arg is preserved here for signature consistency with the rest
of the intent layer but is ignored inside.
"""
from typing import Any
from uuid import UUID

from ..services import file_index as file_index_svc
from ..services import storage as svc


async def list_files(
    user_id: UUID, prefix: str = "", *, limit: int = 200
) -> list[dict[str, Any]]:
    return await svc.list_files(user_id, prefix, limit=limit)


async def list_recursive(user_id: UUID, prefix: str) -> list[str]:
    return await svc.list_recursive(user_id, prefix)


async def download(user_id: UUID, path: str) -> bytes:
    return await svc.download(user_id, path)


async def exists(user_id: UUID, path: str) -> bool:
    return await svc.exists(user_id, path)


async def stat(user_id: UUID, path: str) -> dict[str, Any] | None:
    return await svc.stat(user_id, path)


async def upload(
    user_id: UUID,
    path: str,
    data: bytes,
    content_type: str = "application/octet-stream",
) -> dict[str, Any]:
    return await svc.upload(user_id, path, data, content_type)


async def delete(user_id: UUID, paths: list[str]) -> dict[str, Any]:
    return await svc.delete(user_id, paths)


async def signed_url(user_id: UUID, path: str, expires_in: int = 3600) -> str:
    return await svc.signed_url(user_id, path, expires_in)


async def signed_upload_url(user_id: UUID, path: str) -> dict[str, Any]:
    return await svc.signed_upload_url(user_id, path)


async def move(user_id: UUID, source: str, destination: str) -> dict[str, Any]:
    return await svc.move(user_id, source, destination)


async def search(user_id: UUID, q: str, limit: int = 20) -> list[dict[str, Any]]:
    return await file_index_svc.search(user_id, q, limit)


async def index_all(user_id: UUID) -> dict[str, Any]:
    # Operator-scoped: index_all walks every user's tree and derives the
    # user_id from each top-level path component. The user_id arg here is
    # preserved for intent-layer consistency but deliberately ignored.
    del user_id
    return await file_index_svc.index_all()
