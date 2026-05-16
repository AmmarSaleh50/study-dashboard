"""Full-text search index over the course tree.

Walks `STUDY_ROOT`, extracts text from PDFs / notebooks / markdown / typst,
and upserts each file's text into the `file_index` table. Search is exposed
via a Postgres function (`search_files`) so ranking and snippet generation
run server-side in one round-trip.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any

from .. import db
from . import storage as storage_svc

log = logging.getLogger(__name__)

# Extensions we know how to extract text from. PPTX deliberately excluded
# until we add python-pptx; not worth the dep weight today.
_INDEXABLE_SUFFIXES = (".pdf", ".md", ".txt", ".typ", ".ipynb")


def _course_code_from_path(path: str) -> str | None:
    """Top-level folder name is treated as the course code.

    The course tree under STUDY_ROOT is `<course-folder>/...`, where
    `<course-folder>` matches a `course.folder_name` in the database. The
    indexer just records the folder name on each file row; courses table
    is the source of truth for the human-readable name + display code.
    """
    if "/" not in path:
        return None
    return path.split("/", 1)[0] or None


def _extract_text(path: str, data: bytes) -> str | None:
    """Return extracted text, or None if extraction failed/unsupported."""
    if path.endswith(".pdf"):
        try:
            import fitz  # pymupdf
        except ImportError as e:
            log.error("pymupdf not installed: %s", e)
            return None
        try:
            doc = fitz.open(stream=data, filetype="pdf")
            chunks = [page.get_text() for page in doc]
            doc.close()
            return "\n".join(chunks)
        except Exception as e:
            log.warning("PDF extract failed for %s: %s", path, e)
            return None
    if path.endswith((".md", ".txt", ".typ")):
        try:
            return data.decode("utf-8", errors="ignore")
        except Exception:
            return None
    if path.endswith(".ipynb"):
        try:
            nb = json.loads(data.decode("utf-8", errors="ignore"))
            cells = nb.get("cells", [])
            parts: list[str] = []
            for c in cells:
                src = c.get("source", "")
                if isinstance(src, list):
                    parts.append("".join(src))
                else:
                    parts.append(str(src))
            return "\n\n".join(parts)
        except Exception as e:
            log.warning("ipynb parse failed for %s: %s", path, e)
            return None
    return None


async def index_all() -> dict[str, Any]:
    """Walk the entire course tree and index any file whose sha256 differs from
    the stored row (or that's not yet indexed). Returns a stats dict."""
    keys = await storage_svc.list_recursive("")

    # Pull existing rows in one go so we don't make 100 round-trips
    existing: dict[str, str] = {}
    try:
        rows = await db.fetch(
            "SELECT path, sha256 FROM file_index LIMIT 10000"
        )
        for row in rows:
            existing[row["path"]] = row.get("sha256") or ""
    except Exception as e:
        log.warning("could not preload existing rows (table may not exist yet): %s", e)

    indexed = 0
    skipped = 0
    failed = 0
    for path in keys:
        if not path.endswith(_INDEXABLE_SUFFIXES):
            skipped += 1
            continue
        try:
            data = await storage_svc.download(path)
        except Exception as e:
            log.warning("download failed %s: %s", path, e)
            failed += 1
            continue
        sha = hashlib.sha256(data).hexdigest()
        if existing.get(path) == sha:
            skipped += 1
            continue
        # _extract_text is CPU-bound (PDF parsing via pymupdf can take
        # hundreds of ms per page). Run it on the threadpool so a
        # large reindex doesn't block the asyncio event loop and stall
        # every other request — health check, dashboard, MCP, OAuth.
        text = await asyncio.to_thread(_extract_text, path, data)
        if text is None:
            failed += 1
            continue
        # Postgres text columns choke on raw NULs; strip them
        text = text.replace("\x00", "")
        try:
            await db.execute(
                """
                INSERT INTO file_index (path, course_code, size, sha256, text_content, indexed_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id, path) DO UPDATE
                   SET course_code = EXCLUDED.course_code,
                       size = EXCLUDED.size,
                       sha256 = EXCLUDED.sha256,
                       text_content = EXCLUDED.text_content,
                       indexed_at = EXCLUDED.indexed_at
                """,
                path,
                _course_code_from_path(path),
                len(data),
                sha,
                text,
                datetime.now(timezone.utc),
            )
            indexed += 1
        except Exception as e:
            log.warning("upsert failed for %s: %s", path, e)
            failed += 1

    # Drop rows whose paths no longer exist on disk
    pruned = 0
    try:
        all_paths = set(keys)
        for stale in [p for p in existing if p not in all_paths]:
            await db.execute(
                "DELETE FROM file_index WHERE path = %s",
                stale,
            )
            pruned += 1
    except Exception as e:
        log.warning("prune phase failed: %s", e)

    return {
        "indexed": indexed,
        "skipped": skipped,
        "failed": failed,
        "pruned": pruned,
        "total_seen": len(keys),
    }


async def search(q: str, limit: int = 20) -> list[dict[str, Any]]:
    """Query the search_files Postgres function. Returns ranked results with snippets."""
    if not q or len(q.strip()) < 2:
        return []
    try:
        return await db.fetch(
            "SELECT * FROM search_files(%s, %s)",
            q.strip(), limit,
        )
    except Exception as e:
        log.warning("search rpc failed: %s", e)
        return []
