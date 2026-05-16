"""Full-text search index over the course tree.

Walks `STUDY_ROOT`, extracts text from PDFs / notebooks / markdown / typst,
and upserts each file's text into the `file_index` table. After Phase 1
the on-disk layout is `STUDY_ROOT/<user_id>/<course>/...` and file_index
rows are scoped to a user via the composite (user_id, path) PK.

`index_all()` is operator-scoped — it walks every user's tree and writes
file_index rows with user_id derived from the top-level directory name.
`search()` is per-user — it filters file_index rows by user_id.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from .. import db
from . import storage as storage_svc

log = logging.getLogger(__name__)

# Extensions we know how to extract text from. PPTX deliberately excluded
# until we add python-pptx; not worth the dep weight today.
_INDEXABLE_SUFFIXES = (".pdf", ".md", ".txt", ".typ", ".ipynb")


def _course_code_from_path(path: str) -> str | None:
    """Top-level folder name under the user root is the course code.

    `path` here is user-relative (no user_id prefix), e.g. `ASB/lec1.pdf`.
    Phase 1 stores file_index.path as `<user_id>/<course>/...`; the caller
    prepends the prefix when persisting. Returns the leading segment or
    None for top-level files.
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


def _list_user_dirs() -> list[UUID]:
    """List every top-level directory under STUDY_ROOT whose name parses as
    a UUID. Skips dotfiles (e.g. `.phase1_migrated` marker) and any other
    non-UUID entries (defensive — keeps stray folders out of the index)."""
    root = Path(storage_svc._root())
    if not root.exists() or not root.is_dir():
        return []
    out: list[UUID] = []
    try:
        for entry in root.iterdir():
            if entry.name.startswith("."):
                continue
            if not entry.is_dir():
                continue
            try:
                out.append(UUID(entry.name))
            except ValueError:
                # Not a UUID-shaped folder; skip silently.
                continue
    except OSError:
        return []
    return out


async def index_all() -> dict[str, Any]:
    """Walk every user's tree under STUDY_ROOT and index any file whose
    sha256 differs from the stored row (or that's not yet indexed). Returns
    a stats dict. Operator-scoped: no user_id arg — user_id is derived
    from the top-level directory name on disk."""
    user_ids = _list_user_dirs()

    # Pull existing rows in one go so we don't make 100 round-trips. Map
    # full path (with user_id prefix) → sha256, since that's how the table
    # is keyed and how we'll DELETE on prune.
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
    total_seen = 0
    seen_full_paths: set[str] = set()

    for user_id in user_ids:
        try:
            user_paths = await storage_svc.list_recursive(user_id, "")
        except Exception as e:
            log.warning("list_recursive failed for user %s: %s", user_id, e)
            continue
        total_seen += len(user_paths)
        prefix = f"{user_id}/"

        for path in user_paths:
            full_path = prefix + path
            seen_full_paths.add(full_path)

            if not path.endswith(_INDEXABLE_SUFFIXES):
                skipped += 1
                continue
            try:
                data = await storage_svc.download(user_id, path)
            except Exception as e:
                log.warning("download failed %s: %s", full_path, e)
                failed += 1
                continue
            sha = hashlib.sha256(data).hexdigest()
            if existing.get(full_path) == sha:
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
                    INSERT INTO file_index (user_id, path, course_code, size, sha256, text_content, indexed_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (user_id, path) DO UPDATE
                       SET course_code = EXCLUDED.course_code,
                           size = EXCLUDED.size,
                           sha256 = EXCLUDED.sha256,
                           text_content = EXCLUDED.text_content,
                           indexed_at = EXCLUDED.indexed_at
                    """,
                    user_id,
                    full_path,
                    _course_code_from_path(path),
                    len(data),
                    sha,
                    text,
                    datetime.now(timezone.utc),
                )
                indexed += 1
            except Exception as e:
                log.warning("upsert failed for %s: %s", full_path, e)
                failed += 1

    # Drop rows whose paths no longer exist on disk
    pruned = 0
    try:
        for stale in [p for p in existing if p not in seen_full_paths]:
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
        "total_seen": total_seen,
    }


async def search(user_id: UUID, q: str, limit: int = 20) -> list[dict[str, Any]]:
    """Full-text search across this user's indexed files.

    Filters by user_id at the SQL layer and returns ranked results with
    ts_headline snippets. Match terms are wrapped in `<<…>>` markers in
    the snippet so the frontend can highlight them.

    The stored `path` in file_index includes a `<user_id>/` prefix (Phase 1
    on-disk layout); we strip it before returning so callers see the same
    user-relative paths the rest of the file API exposes.
    """
    if not q or len(q.strip()) < 2:
        return []
    try:
        rows = await db.fetch(
            """
            WITH query AS (
              SELECT websearch_to_tsquery('simple', %s) AS tsq
            )
            SELECT
              f.path,
              f.course_code,
              f.size,
              ts_rank(f.search_vector, query.tsq) AS rank,
              ts_headline(
                'simple',
                f.text_content,
                query.tsq,
                'StartSel=<<,StopSel=>>,MaxFragments=2,MaxWords=15,MinWords=5,FragmentDelimiter=" … "'
              ) AS snippet
            FROM file_index f, query
            WHERE f.user_id = %s
              AND f.search_vector @@ query.tsq
            ORDER BY rank DESC
            LIMIT %s
            """,
            q.strip(), user_id, limit,
        )
    except Exception as e:
        log.warning("search query failed: %s", e)
        return []

    prefix = f"{user_id}/"
    out: list[dict[str, Any]] = []
    for row in rows:
        # Strip the user_id prefix from path so the API surface stays
        # user-relative. Rows seeded without a prefix (legacy data, tests
        # that INSERT raw) just pass through unmodified.
        path = row.get("path") or ""
        if path.startswith(prefix):
            row = {**row, "path": path[len(prefix):]}
        out.append(row)
    return out
