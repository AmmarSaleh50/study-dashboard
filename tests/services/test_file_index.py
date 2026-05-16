"""Tests for app/services/file_index.py.

The indexer walks `STUDY_ROOT/<user_id>/...` and writes per-user rows to
`file_index`. Filesystem state is per-test via `tmp_path` + monkeypatched
`STUDY_ROOT`; the `study_root` fixture pre-creates the sentinel user's
subdir so tests can write straight into it. The async pool is wired via
the `client` fixture.

`index_all()` is operator-scoped — it walks every user dir and derives
`user_id` from the top-level folder name. `search(user_id, ...)` filters
file_index rows by user_id. file_index rows are keyed (user_id, path)
with `path` including the `<user_id>/` prefix per the Phase 1 migration.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.auth import SENTINEL_USER_ID


@pytest.fixture
def study_root(tmp_path, monkeypatch):
    """Point STUDY_ROOT at a per-test directory and pre-create the sentinel
    user's subdir. Tests write files into `study_root/...` (the user dir),
    not `tmp_path/...`."""
    monkeypatch.setenv("STUDY_ROOT", str(tmp_path))
    user_dir: Path = tmp_path / str(SENTINEL_USER_ID)
    user_dir.mkdir(parents=True, exist_ok=True)
    return user_dir


def _full_path(rel: str) -> str:
    """Build the file_index.path value the indexer will write: prefix
    user_id + user-relative path."""
    return f"{SENTINEL_USER_ID}/{rel}"


async def _clear_file_index(db_conn) -> None:
    """Wipe file_index between tests since each function-scoped pool reuses
    the session-scoped testcontainer."""
    async with db_conn.connection() as conn, conn.cursor() as cur:
        await cur.execute("DELETE FROM file_index")


async def _count_rows(db_conn) -> int:
    async with db_conn.connection() as conn, conn.cursor() as cur:
        await cur.execute("SELECT count(*) AS n FROM file_index")
        row = await cur.fetchone()
        return int(row["n"])


# A tiny real PDF so pymupdf has something legal to parse. Built once via
# `fitz.open()` + a single empty page; the bytes are stable so we hard-code.
def _make_pdf(text: str = "Hello PDF") -> bytes:
    import fitz  # pymupdf
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    data = doc.tobytes()
    doc.close()
    return data


# ── index_all ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_index_all_empty_root(client, db_conn, study_root):
    """An empty user tree indexes nothing and returns zero stats."""
    from app.services import file_index as svc
    await _clear_file_index(db_conn)

    stats = await svc.index_all()

    assert stats["indexed"] == 0
    assert stats["skipped"] == 0
    assert stats["failed"] == 0
    assert stats["pruned"] == 0
    assert stats["total_seen"] == 0
    assert await _count_rows(db_conn) == 0


@pytest.mark.asyncio
async def test_index_all_indexes_one_pdf(client, db_conn, study_root):
    """A single .pdf under a course folder gets indexed; row reflects content
    and stored path includes the user_id prefix."""
    from app.services import file_index as svc
    await _clear_file_index(db_conn)
    (study_root / "ASB").mkdir()
    pdf_bytes = _make_pdf("Quantum mechanics overview")
    (study_root / "ASB" / "lecture1.pdf").write_bytes(pdf_bytes)

    stats = await svc.index_all()

    assert stats["indexed"] == 1
    assert stats["failed"] == 0
    assert stats["total_seen"] == 1
    async with db_conn.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT path, course_code, size, sha256, text_content, user_id "
            "FROM file_index WHERE path = %s",
            (_full_path("ASB/lecture1.pdf"),),
        )
        row = await cur.fetchone()
    assert row is not None
    assert row["course_code"] == "ASB"
    assert row["size"] == len(pdf_bytes)
    assert row["sha256"] and len(row["sha256"]) == 64
    assert "Quantum" in row["text_content"]
    assert str(row["user_id"]) == str(SENTINEL_USER_ID)


@pytest.mark.asyncio
async def test_index_all_indexes_one_md(client, db_conn, study_root):
    """A markdown file is indexed by raw decode."""
    from app.services import file_index as svc
    await _clear_file_index(db_conn)
    (study_root / "CS101").mkdir()
    md = "# Notes\nSome **markdown** content for tests."
    (study_root / "CS101" / "notes.md").write_text(md, encoding="utf-8")

    stats = await svc.index_all()

    assert stats["indexed"] == 1
    async with db_conn.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT text_content, course_code FROM file_index "
            "WHERE path = %s",
            (_full_path("CS101/notes.md"),),
        )
        row = await cur.fetchone()
    assert row is not None
    assert row["course_code"] == "CS101"
    assert "markdown" in row["text_content"]


@pytest.mark.asyncio
async def test_index_all_skips_unchanged_sha(client, db_conn, study_root):
    """Re-running with no file changes leaves all rows alone (skipped)."""
    from app.services import file_index as svc
    await _clear_file_index(db_conn)
    (study_root / "ASB").mkdir()
    (study_root / "ASB" / "a.md").write_text("hello", encoding="utf-8")

    first = await svc.index_all()
    assert first["indexed"] == 1

    second = await svc.index_all()
    assert second["indexed"] == 0
    # 1 indexable file present, sha matches → counted as skipped.
    assert second["skipped"] == 1
    assert second["total_seen"] == 1


@pytest.mark.asyncio
async def test_index_all_prunes_removed_files(client, db_conn, study_root):
    """Files removed from disk are dropped from file_index on the next pass."""
    from app.services import file_index as svc
    await _clear_file_index(db_conn)
    (study_root / "ASB").mkdir()
    (study_root / "ASB" / "stays.md").write_text("kept", encoding="utf-8")
    (study_root / "ASB" / "goes.md").write_text("removed", encoding="utf-8")

    first = await svc.index_all()
    assert first["indexed"] == 2

    # Remove one file and re-index
    (study_root / "ASB" / "goes.md").unlink()
    second = await svc.index_all()

    assert second["pruned"] == 1
    async with db_conn.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT path FROM file_index ORDER BY path"
        )
        rows = await cur.fetchall()
    paths = [r["path"] for r in rows]
    assert paths == [_full_path("ASB/stays.md")]


@pytest.mark.asyncio
async def test_index_all_skips_non_indexable_extensions(client, db_conn, study_root):
    """Files with non-indexable suffixes are counted as `skipped`, not indexed."""
    from app.services import file_index as svc
    await _clear_file_index(db_conn)
    (study_root / "ASB").mkdir()
    (study_root / "ASB" / "image.jpg").write_bytes(b"\xff\xd8\xff")
    (study_root / "ASB" / "data.csv").write_text("a,b,c\n", encoding="utf-8")
    (study_root / "ASB" / "notes.md").write_text("ok", encoding="utf-8")

    stats = await svc.index_all()

    assert stats["indexed"] == 1  # only notes.md
    assert stats["skipped"] == 2  # jpg + csv
    assert stats["total_seen"] == 3
    assert await _count_rows(db_conn) == 1


@pytest.mark.asyncio
async def test_index_all_failed_pdf_extract_does_not_crash(
    client, db_conn, study_root
):
    """A malformed .pdf bumps `failed` — the indexer doesn't abort the run."""
    from app.services import file_index as svc
    await _clear_file_index(db_conn)
    (study_root / "ASB").mkdir()
    # garbage bytes that aren't a real PDF
    (study_root / "ASB" / "broken.pdf").write_bytes(b"not actually a pdf")
    # a legitimate file alongside it
    (study_root / "ASB" / "good.md").write_text("good", encoding="utf-8")

    stats = await svc.index_all()

    assert stats["indexed"] == 1
    assert stats["failed"] == 1
    assert stats["total_seen"] == 2
    async with db_conn.connection() as conn, conn.cursor() as cur:
        await cur.execute("SELECT path FROM file_index")
        rows = await cur.fetchall()
    paths = {r["path"] for r in rows}
    assert paths == {_full_path("ASB/good.md")}


@pytest.mark.asyncio
async def test_index_all_indexes_ipynb(client, db_conn, study_root):
    """`.ipynb` notebooks: cell sources are concatenated into text_content."""
    from app.services import file_index as svc
    await _clear_file_index(db_conn)
    (study_root / "CS101").mkdir()
    nb = {
        "cells": [
            {"cell_type": "markdown", "source": ["# Title\n", "Intro text\n"]},
            {"cell_type": "code", "source": "print('hello')"},
        ],
        "metadata": {},
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    (study_root / "CS101" / "lab.ipynb").write_text(
        json.dumps(nb), encoding="utf-8"
    )

    stats = await svc.index_all()

    assert stats["indexed"] == 1
    async with db_conn.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT text_content FROM file_index WHERE path = %s",
            (_full_path("CS101/lab.ipynb"),),
        )
        row = await cur.fetchone()
    assert row is not None
    assert "Title" in row["text_content"]
    assert "print('hello')" in row["text_content"]


@pytest.mark.asyncio
async def test_index_all_skips_dotfile_marker(client, db_conn, study_root, tmp_path):
    """Dot-prefixed top-level entries (e.g. `.phase1_migrated`) and non-UUID
    folders are silently skipped — only UUID-shaped user dirs are walked."""
    from app.services import file_index as svc
    await _clear_file_index(db_conn)
    # Marker file at STUDY_ROOT (sibling of the user dir) should be ignored.
    (tmp_path / ".phase1_migrated").write_text("2026-05-16", encoding="utf-8")
    # Stray non-UUID folder at STUDY_ROOT — ignored too.
    (tmp_path / "stray_folder").mkdir()
    (tmp_path / "stray_folder" / "ignored.md").write_text("nope", encoding="utf-8")
    # A legit file under the sentinel user — should index.
    (study_root / "ASB").mkdir()
    (study_root / "ASB" / "real.md").write_text("ok", encoding="utf-8")

    stats = await svc.index_all()

    assert stats["indexed"] == 1
    assert stats["total_seen"] == 1
    async with db_conn.connection() as conn, conn.cursor() as cur:
        await cur.execute("SELECT path FROM file_index ORDER BY path")
        rows = await cur.fetchall()
    paths = [r["path"] for r in rows]
    assert paths == [_full_path("ASB/real.md")]


# ── search (per-user filter) ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_search_short_query_returns_empty(client, db_conn):
    """Queries shorter than 2 chars short-circuit without hitting the DB."""
    from app.services import file_index as svc
    assert await svc.search(SENTINEL_USER_ID, "") == []
    assert await svc.search(SENTINEL_USER_ID, "a") == []
    assert await svc.search(SENTINEL_USER_ID, "   ") == []


@pytest.mark.asyncio
async def test_search_returns_matching_rows(client, db_conn):
    """A row whose text_content matches the query comes back, scoped to the user."""
    from app.services import file_index as svc
    await _clear_file_index(db_conn)
    # Seed file_index directly — search() doesn't need actual files on disk.
    # user_id defaults to the sentinel (Phase 1 column default).
    async with db_conn.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "INSERT INTO file_index (path, course_code, size, sha256, "
            "text_content) VALUES (%s, %s, %s, %s, %s)",
            (_full_path("ASB/quantum.md"), "ASB", 100, "deadbeef" * 8,
             "Quantum mechanics is the study of subatomic particles."),
        )
        await cur.execute(
            "INSERT INTO file_index (path, course_code, size, sha256, "
            "text_content) VALUES (%s, %s, %s, %s, %s)",
            (_full_path("ASB/biology.md"), "ASB", 100, "cafe" * 16,
             "Photosynthesis converts light to chemical energy."),
        )

    rows = await svc.search(SENTINEL_USER_ID, "quantum mechanics", limit=10)

    assert len(rows) == 1
    # The user_id prefix is stripped from `path` in the response.
    assert rows[0]["path"] == "ASB/quantum.md"
    assert rows[0]["course_code"] == "ASB"
    # snippet wraps matches in << >>
    assert "<<" in rows[0]["snippet"] or ">>" in rows[0]["snippet"]
    assert isinstance(rows[0]["rank"], float)


@pytest.mark.asyncio
async def test_search_filters_by_user_id(client, db_conn):
    """Rows belonging to another user must NOT show up in this user's search."""
    from uuid import uuid4

    from app.services import file_index as svc
    await _clear_file_index(db_conn)

    other_user = uuid4()
    # First, ensure a users row exists for `other_user` (FK).
    async with db_conn.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "INSERT INTO users (id, email, display_name) VALUES (%s, %s, %s) "
            "ON CONFLICT DO NOTHING",
            (other_user, f"{other_user}@example.test", "Other User"),
        )
        # Two rows with the same text content, different users.
        await cur.execute(
            "INSERT INTO file_index (user_id, path, course_code, size, sha256, "
            "text_content) VALUES (%s, %s, %s, %s, %s, %s)",
            (SENTINEL_USER_ID, _full_path("ASB/mine.md"), "ASB", 50,
             "a" * 64, "Photosynthesis converts light to chemical energy."),
        )
        await cur.execute(
            "INSERT INTO file_index (user_id, path, course_code, size, sha256, "
            "text_content) VALUES (%s, %s, %s, %s, %s, %s)",
            (other_user, f"{other_user}/ASB/theirs.md", "ASB", 50,
             "b" * 64, "Photosynthesis converts light to chemical energy."),
        )

    mine = await svc.search(SENTINEL_USER_ID, "photosynthesis", limit=10)
    assert [r["path"] for r in mine] == ["ASB/mine.md"]

    theirs = await svc.search(other_user, "photosynthesis", limit=10)
    assert [r["path"] for r in theirs] == ["ASB/theirs.md"]


@pytest.mark.asyncio
async def test_search_no_matches_returns_empty(client, db_conn):
    """A non-matching query returns []."""
    from app.services import file_index as svc
    await _clear_file_index(db_conn)
    async with db_conn.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "INSERT INTO file_index (path, course_code, size, sha256, "
            "text_content) VALUES (%s, %s, %s, %s, %s)",
            (_full_path("ASB/note.md"), "ASB", 10, "f" * 64, "A short text content."),
        )

    rows = await svc.search(SENTINEL_USER_ID, "xyzzy_no_such_word", limit=10)

    assert rows == []


@pytest.mark.asyncio
async def test_search_respects_limit(client, db_conn):
    """`limit` caps the number of results from the query."""
    from app.services import file_index as svc
    await _clear_file_index(db_conn)
    async with db_conn.connection() as conn, conn.cursor() as cur:
        for i in range(5):
            await cur.execute(
                "INSERT INTO file_index (path, course_code, size, sha256, "
                "text_content) VALUES (%s, %s, %s, %s, %s)",
                (_full_path(f"ASB/note{i}.md"), "ASB", 10, f"{i:0>64}",
                 "Photosynthesis converts light to chemical energy."),
            )

    rows = await svc.search(SENTINEL_USER_ID, "photosynthesis", limit=2)
    assert len(rows) == 2
