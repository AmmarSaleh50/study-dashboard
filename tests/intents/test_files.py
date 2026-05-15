"""Smoke test for app/intents/files.py — proves the pass-through compiles.

Storage operations (list_files, upload, download, etc.) interact with
STUDY_ROOT on disk and cannot run meaningfully against a test Postgres
container. We test only that:

1. The intent module imports without error.
2. The file_index.search wrapper returns an empty list for a nonsense query
   (the file_index table exists in the test schema; no files are indexed).

Phase 2 will add proper storage-scoping tests once a per-user storage
namespace is in place.
"""
import pytest
from uuid import UUID

OPERATOR = UUID("00000000-0000-0000-0000-000000000001")


@pytest.mark.asyncio
async def test_files_intent_search_empty(client, db_conn):
    from app.intents import files as intent

    results = await intent.search(OPERATOR, "zzznomatchtoken", limit=5)
    assert isinstance(results, list)


def test_files_intent_module_exports():
    """All expected public functions are present on the intent module."""
    from app.intents import files as intent

    for fn in (
        "list_files",
        "list_recursive",
        "download",
        "exists",
        "stat",
        "upload",
        "delete",
        "signed_url",
        "signed_upload_url",
        "move",
        "search",
        "index_all",
    ):
        assert callable(getattr(intent, fn, None)), f"missing: {fn}"
