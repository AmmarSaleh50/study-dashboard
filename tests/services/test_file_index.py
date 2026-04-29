"""Tests for app/services/file_index.py.

The indexer walks `STUDY_ROOT`, hashes each indexable file, extracts text,
and upserts a row into `file_index`. Filesystem state is per-test via
`tmp_path` + monkeypatched `STUDY_ROOT`. The async pool is wired via the
`client` fixture.

`search()` calls the `search_files` Postgres function (defined in
baseline.sql; uses `to_tsvector`/`websearch_to_tsquery` from the built-in
`simple` config — no extension needed). All search tests run inside the
testcontainer.
"""
from __future__ import annotations

import json

import pytest


@pytest.fixture
def study_root(tmp_path, monkeypatch):
    """Point STUDY_ROOT at a per-test directory."""
    monkeypatch.setenv("STUDY_ROOT", str(tmp_path))
    return tmp_path


async def _clear_file_index(db_pool) -> None:
    """Wipe file_index between tests since each function-scoped pool reuses
    the session-scoped testcontainer."""
    async with db_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute("DELETE FROM file_index")


async def _count_rows(db_pool) -> int:
    async with db_pool.connection() as conn, conn.cursor() as cur:
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
async def test_index_all_empty_root(client, db_pool, study_root):
    """An empty STUDY_ROOT indexes nothing and returns zero stats."""
    from app.services import file_index as svc
    await _clear_file_index(db_pool)

    stats = await svc.index_all()

    assert stats["indexed"] == 0
    assert stats["skipped"] == 0
    assert stats["failed"] == 0
    assert stats["pruned"] == 0
    assert stats["total_seen"] == 0
    assert await _count_rows(db_pool) == 0


@pytest.mark.asyncio
async def test_index_all_indexes_one_pdf(client, db_pool, study_root):
    """A single .pdf under a course folder gets indexed; row reflects content."""
    from app.services import file_index as svc
    await _clear_file_index(db_pool)
    (study_root / "ASB").mkdir()
    pdf_bytes = _make_pdf("Quantum mechanics overview")
    (study_root / "ASB" / "lecture1.pdf").write_bytes(pdf_bytes)

    stats = await svc.index_all()

    assert stats["indexed"] == 1
    assert stats["failed"] == 0
    assert stats["total_seen"] == 1
    async with db_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT path, course_code, size, sha256, text_content "
            "FROM file_index WHERE path = %s",
            ("ASB/lecture1.pdf",),
        )
        row = await cur.fetchone()
    assert row is not None
    assert row["course_code"] == "ASB"
    assert row["size"] == len(pdf_bytes)
    assert row["sha256"] and len(row["sha256"]) == 64
    assert "Quantum" in row["text_content"]


@pytest.mark.asyncio
async def test_index_all_indexes_one_md(client, db_pool, study_root):
    """A markdown file is indexed by raw decode."""
    from app.services import file_index as svc
    await _clear_file_index(db_pool)
    (study_root / "CS101").mkdir()
    md = "# Notes\nSome **markdown** content for tests."
    (study_root / "CS101" / "notes.md").write_text(md, encoding="utf-8")

    stats = await svc.index_all()

    assert stats["indexed"] == 1
    async with db_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT text_content, course_code FROM file_index "
            "WHERE path = %s",
            ("CS101/notes.md",),
        )
        row = await cur.fetchone()
    assert row is not None
    assert row["course_code"] == "CS101"
    assert "markdown" in row["text_content"]


@pytest.mark.asyncio
async def test_index_all_skips_unchanged_sha(client, db_pool, study_root):
    """Re-running with no file changes leaves all rows alone (skipped)."""
    from app.services import file_index as svc
    await _clear_file_index(db_pool)
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
async def test_index_all_prunes_removed_files(client, db_pool, study_root):
    """Files removed from disk are dropped from file_index on the next pass."""
    from app.services import file_index as svc
    await _clear_file_index(db_pool)
    (study_root / "ASB").mkdir()
    (study_root / "ASB" / "stays.md").write_text("kept", encoding="utf-8")
    (study_root / "ASB" / "goes.md").write_text("removed", encoding="utf-8")

    first = await svc.index_all()
    assert first["indexed"] == 2

    # Remove one file and re-index
    (study_root / "ASB" / "goes.md").unlink()
    second = await svc.index_all()

    assert second["pruned"] == 1
    async with db_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT path FROM file_index ORDER BY path"
        )
        rows = await cur.fetchall()
    paths = [r["path"] for r in rows]
    assert paths == ["ASB/stays.md"]


@pytest.mark.asyncio
async def test_index_all_skips_non_indexable_extensions(client, db_pool, study_root):
    """Files with non-indexable suffixes are counted as `skipped`, not indexed."""
    from app.services import file_index as svc
    await _clear_file_index(db_pool)
    (study_root / "ASB").mkdir()
    (study_root / "ASB" / "image.jpg").write_bytes(b"\xff\xd8\xff")
    (study_root / "ASB" / "data.csv").write_text("a,b,c\n", encoding="utf-8")
    (study_root / "ASB" / "notes.md").write_text("ok", encoding="utf-8")

    stats = await svc.index_all()

    assert stats["indexed"] == 1  # only notes.md
    assert stats["skipped"] == 2  # jpg + csv
    assert stats["total_seen"] == 3
    assert await _count_rows(db_pool) == 1


@pytest.mark.asyncio
async def test_index_all_failed_pdf_extract_does_not_crash(
    client, db_pool, study_root
):
    """A malformed .pdf bumps `failed` — the indexer doesn't abort the run."""
    from app.services import file_index as svc
    await _clear_file_index(db_pool)
    (study_root / "ASB").mkdir()
    # garbage bytes that aren't a real PDF
    (study_root / "ASB" / "broken.pdf").write_bytes(b"not actually a pdf")
    # a legitimate file alongside it
    (study_root / "ASB" / "good.md").write_text("good", encoding="utf-8")

    stats = await svc.index_all()

    assert stats["indexed"] == 1
    assert stats["failed"] == 1
    assert stats["total_seen"] == 2
    async with db_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute("SELECT path FROM file_index")
        rows = await cur.fetchall()
    paths = {r["path"] for r in rows}
    assert paths == {"ASB/good.md"}


@pytest.mark.asyncio
async def test_index_all_indexes_ipynb(client, db_pool, study_root):
    """`.ipynb` notebooks: cell sources are concatenated into text_content."""
    from app.services import file_index as svc
    await _clear_file_index(db_pool)
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
    async with db_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT text_content FROM file_index WHERE path = %s",
            ("CS101/lab.ipynb",),
        )
        row = await cur.fetchone()
    assert row is not None
    assert "Title" in row["text_content"]
    assert "print('hello')" in row["text_content"]


# ── search (search_files RPC) ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_search_short_query_returns_empty(client, db_pool):
    """Queries shorter than 2 chars short-circuit without hitting the DB."""
    from app.services import file_index as svc
    assert await svc.search("") == []
    assert await svc.search("a") == []
    assert await svc.search("   ") == []


@pytest.mark.asyncio
async def test_search_returns_matching_rows(client, db_pool):
    """A row whose text_content matches the query comes back via the RPC."""
    from app.services import file_index as svc
    await _clear_file_index(db_pool)
    # Seed file_index directly — search() doesn't need actual files on disk.
    async with db_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "INSERT INTO file_index (path, course_code, size, sha256, "
            "text_content) VALUES (%s, %s, %s, %s, %s)",
            ("ASB/quantum.md", "ASB", 100, "deadbeef" * 8,
             "Quantum mechanics is the study of subatomic particles."),
        )
        await cur.execute(
            "INSERT INTO file_index (path, course_code, size, sha256, "
            "text_content) VALUES (%s, %s, %s, %s, %s)",
            ("ASB/biology.md", "ASB", 100, "cafe" * 16,
             "Photosynthesis converts light to chemical energy."),
        )

    rows = await svc.search("quantum mechanics", limit=10)

    assert len(rows) == 1
    assert rows[0]["path"] == "ASB/quantum.md"
    assert rows[0]["course_code"] == "ASB"
    # snippet wraps matches in << >>
    assert "<<" in rows[0]["snippet"] or ">>" in rows[0]["snippet"]
    assert isinstance(rows[0]["rank"], float)


@pytest.mark.asyncio
async def test_search_no_matches_returns_empty(client, db_pool):
    """A non-matching query returns []."""
    from app.services import file_index as svc
    await _clear_file_index(db_pool)
    async with db_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "INSERT INTO file_index (path, course_code, size, sha256, "
            "text_content) VALUES (%s, %s, %s, %s, %s)",
            ("ASB/note.md", "ASB", 10, "f" * 64, "A short text content."),
        )

    rows = await svc.search("xyzzy_no_such_word", limit=10)

    assert rows == []


@pytest.mark.asyncio
async def test_search_respects_limit(client, db_pool):
    """`limit` caps the number of results from the RPC."""
    from app.services import file_index as svc
    await _clear_file_index(db_pool)
    async with db_pool.connection() as conn, conn.cursor() as cur:
        for i in range(5):
            await cur.execute(
                "INSERT INTO file_index (path, course_code, size, sha256, "
                "text_content) VALUES (%s, %s, %s, %s, %s)",
                (f"ASB/note{i}.md", "ASB", 10, f"{i:0>64}",
                 "Photosynthesis converts light to chemical energy."),
            )

    rows = await svc.search("photosynthesis", limit=2)
    assert len(rows) == 2
