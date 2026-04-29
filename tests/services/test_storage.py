"""Tests for app/services/storage.py.

Storage is filesystem-backed: every test gets its own `tmp_path` and points
`STUDY_ROOT` there via monkeypatch. Each public function is `async def` so
it's awaitable from `app/services/file_index.py` (which threads sync
extraction work) and the FastAPI router handlers.

`_log()` writes to the `events` table via the async pool — these tests use
the `client` fixture so the pool is wired to the testcontainer. The course
code derived from path payload (Batch A behaviour) is asserted directly
against the resulting events row.

External integrations (signed URLs, cloud storage) are NOT covered here —
the current implementation returns same-origin in-app paths, so there's
nothing external to mock.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def study_root(tmp_path, monkeypatch):
    """Point STUDY_ROOT at a per-test directory."""
    monkeypatch.setenv("STUDY_ROOT", str(tmp_path))
    return tmp_path


# ── list_files ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_files_empty_root_returns_empty(client, db_pool, study_root):
    from app.services import storage as svc
    result = await svc.list_files("")
    assert result == []


@pytest.mark.asyncio
async def test_list_files_returns_files_and_folders(client, db_pool, study_root):
    """Folder entries get id=None; file entries get id + size + mimetype."""
    from app.services import storage as svc
    (study_root / "folder").mkdir()
    (study_root / "a.txt").write_text("hello", encoding="utf-8")
    (study_root / "b.pdf").write_bytes(b"%PDF-1.4 stub")

    result = await svc.list_files("")
    names = [e["name"] for e in result]
    assert "folder" in names
    assert "a.txt" in names
    assert "b.pdf" in names
    by_name = {e["name"]: e for e in result}
    assert by_name["folder"]["id"] is None
    assert by_name["folder"]["metadata"] is None
    assert by_name["a.txt"]["id"] is not None
    assert by_name["a.txt"]["metadata"]["size"] == 5
    assert by_name["a.txt"]["metadata"]["mimetype"] == "text/plain"
    assert by_name["b.pdf"]["metadata"]["mimetype"] == "application/pdf"


@pytest.mark.asyncio
async def test_list_files_filters_dotfiles(client, db_pool, study_root):
    """Anything starting with `.` is hidden from listings."""
    from app.services import storage as svc
    (study_root / "visible.txt").write_text("v", encoding="utf-8")
    (study_root / ".hidden").write_text("h", encoding="utf-8")
    (study_root / ".keep").write_text("", encoding="utf-8")

    result = await svc.list_files("")
    names = [e["name"] for e in result]
    assert "visible.txt" in names
    assert ".hidden" not in names
    assert ".keep" not in names


@pytest.mark.asyncio
async def test_list_files_at_subprefix(client, db_pool, study_root):
    """Listing a subfolder returns only its direct children."""
    from app.services import storage as svc
    (study_root / "ASB").mkdir()
    (study_root / "ASB" / "lecture1.pdf").write_bytes(b"x")
    (study_root / "ASB" / "subfolder").mkdir()

    result = await svc.list_files("ASB")
    names = [e["name"] for e in result]
    assert names == sorted(names, key=str.lower)
    assert "lecture1.pdf" in names
    assert "subfolder" in names


@pytest.mark.asyncio
async def test_list_files_invalid_prefix_returns_empty(client, db_pool, study_root):
    """`..` traversal attempts return [] rather than raising."""
    from app.services import storage as svc
    result = await svc.list_files("../etc")
    assert result == []


# ── list_recursive ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_recursive_descends_subfolders(client, db_pool, study_root):
    """Walks every level under prefix, returns relative paths with `/` separators."""
    from app.services import storage as svc
    (study_root / "ASB").mkdir()
    (study_root / "ASB" / "lec.pdf").write_bytes(b"x")
    (study_root / "ASB" / "sub").mkdir()
    (study_root / "ASB" / "sub" / "deeper.txt").write_text("y", encoding="utf-8")

    result = await svc.list_recursive("ASB")
    assert "ASB/lec.pdf" in result
    assert "ASB/sub/deeper.txt" in result


@pytest.mark.asyncio
async def test_list_recursive_skips_dotfiles(client, db_pool, study_root):
    """Dot-prefixed files anywhere in the tree are excluded."""
    from app.services import storage as svc
    (study_root / "ASB").mkdir()
    (study_root / "ASB" / "real.txt").write_text("ok", encoding="utf-8")
    (study_root / "ASB" / ".keep").write_text("", encoding="utf-8")
    (study_root / "ASB" / ".git").mkdir()
    (study_root / "ASB" / ".git" / "HEAD").write_text("ref", encoding="utf-8")

    result = await svc.list_recursive("ASB")
    assert "ASB/real.txt" in result
    assert all(".keep" not in p and ".git" not in p for p in result)


@pytest.mark.asyncio
async def test_list_recursive_invalid_prefix_returns_empty(client, db_pool, study_root):
    from app.services import storage as svc
    result = await svc.list_recursive("../escape")
    assert result == []


# ── download / exists / stat ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_download_returns_bytes(client, db_pool, study_root):
    from app.services import storage as svc
    (study_root / "a.txt").write_bytes(b"hello world")
    data = await svc.download("a.txt")
    assert data == b"hello world"


@pytest.mark.asyncio
async def test_download_missing_raises(client, db_pool, study_root):
    from app.services import storage as svc
    with pytest.raises(FileNotFoundError):
        await svc.download("does_not_exist.txt")


@pytest.mark.asyncio
async def test_download_path_escape_raises(client, db_pool, study_root):
    """`..` traversal must not let us read outside STUDY_ROOT."""
    from app.services import storage as svc
    with pytest.raises(ValueError):
        await svc.download("../../etc/passwd")


@pytest.mark.asyncio
async def test_exists_true_for_file(client, db_pool, study_root):
    from app.services import storage as svc
    (study_root / "x.txt").write_bytes(b"x")
    assert await svc.exists("x.txt") is True


@pytest.mark.asyncio
async def test_exists_false_for_missing(client, db_pool, study_root):
    from app.services import storage as svc
    assert await svc.exists("nope.txt") is False


@pytest.mark.asyncio
async def test_exists_false_for_traversal(client, db_pool, study_root):
    from app.services import storage as svc
    assert await svc.exists("../../etc/passwd") is False


@pytest.mark.asyncio
async def test_stat_returns_metadata(client, db_pool, study_root):
    from app.services import storage as svc
    (study_root / "a.pdf").write_bytes(b"%PDF-1.4 stub")
    meta = await svc.stat("a.pdf")
    assert meta is not None
    assert meta["path"] == "a.pdf"
    assert meta["size"] == len(b"%PDF-1.4 stub")
    assert meta["mimetype"] == "application/pdf"
    assert "updated_at" in meta


@pytest.mark.asyncio
async def test_stat_missing_returns_none(client, db_pool, study_root):
    from app.services import storage as svc
    assert await svc.stat("nope.txt") is None


# ── upload / delete / move ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_upload_round_trip(client, db_pool, study_root):
    """upload → download returns identical bytes; size matches."""
    from app.services import storage as svc
    payload = b"binary data \x00 \xff\xfe round trip"
    result = await svc.upload("ASB/lecture.pdf", payload, content_type="application/pdf")
    assert result == {
        "path": "ASB/lecture.pdf",
        "size": len(payload),
        "content_type": "application/pdf",
    }
    # File actually exists on disk
    assert (study_root / "ASB" / "lecture.pdf").read_bytes() == payload
    # And download() retrieves the same bytes
    assert await svc.download("ASB/lecture.pdf") == payload


@pytest.mark.asyncio
async def test_upload_creates_parent_dirs(client, db_pool, study_root):
    """Nested paths auto-create parent folders."""
    from app.services import storage as svc
    await svc.upload("a/b/c/file.txt", b"x")
    assert (study_root / "a" / "b" / "c" / "file.txt").read_bytes() == b"x"


@pytest.mark.asyncio
async def test_upload_overwrites_existing(client, db_pool, study_root):
    """Re-uploading the same path replaces the old contents atomically."""
    from app.services import storage as svc
    await svc.upload("a.txt", b"first")
    await svc.upload("a.txt", b"second")
    assert (study_root / "a.txt").read_bytes() == b"second"


@pytest.mark.asyncio
async def test_delete_removes_file(client, db_pool, study_root):
    from app.services import storage as svc
    (study_root / "a.txt").write_bytes(b"x")
    result = await svc.delete(["a.txt"])
    assert result == {"deleted": ["a.txt"]}
    assert not (study_root / "a.txt").exists()


@pytest.mark.asyncio
async def test_delete_missing_is_idempotent(client, db_pool, study_root):
    """Missing paths silently skip — no exception, no count."""
    from app.services import storage as svc
    result = await svc.delete(["never_existed.txt"])
    assert result == {"deleted": []}


@pytest.mark.asyncio
async def test_delete_skips_traversal(client, db_pool, study_root):
    """Paths that escape STUDY_ROOT are silently skipped, not deleted."""
    from app.services import storage as svc
    (study_root / "real.txt").write_bytes(b"x")
    result = await svc.delete(["../../etc/passwd", "real.txt"])
    assert result == {"deleted": ["real.txt"]}


@pytest.mark.asyncio
async def test_move_renames_file(client, db_pool, study_root):
    from app.services import storage as svc
    (study_root / "a.txt").write_bytes(b"hello")
    result = await svc.move("a.txt", "b.txt")
    assert result == {"from": "a.txt", "to": "b.txt"}
    assert not (study_root / "a.txt").exists()
    assert (study_root / "b.txt").read_bytes() == b"hello"


@pytest.mark.asyncio
async def test_move_across_directories(client, db_pool, study_root):
    """Cross-folder moves auto-create the destination directory."""
    from app.services import storage as svc
    (study_root / "src").mkdir()
    (study_root / "src" / "x.txt").write_bytes(b"data")
    await svc.move("src/x.txt", "dst/y.txt")
    assert (study_root / "dst" / "y.txt").read_bytes() == b"data"


@pytest.mark.asyncio
async def test_move_missing_source_raises(client, db_pool, study_root):
    from app.services import storage as svc
    with pytest.raises(FileNotFoundError):
        await svc.move("nope.txt", "anywhere.txt")


# ── signed URLs (in-app, no external dependency) ─────────────────────────────


@pytest.mark.asyncio
async def test_signed_url_for_existing_file(client, db_pool, study_root):
    from app.services import storage as svc
    (study_root / "doc.pdf").write_bytes(b"%PDF-1.4")
    url = await svc.signed_url("doc.pdf")
    # Same-origin path that hits the raw streamer.
    assert url.startswith("/api/files/raw?path=")
    assert "doc.pdf" in url


@pytest.mark.asyncio
async def test_signed_url_missing_raises(client, db_pool, study_root):
    from app.services import storage as svc
    with pytest.raises(FileNotFoundError):
        await svc.signed_url("nope.pdf")


@pytest.mark.asyncio
async def test_signed_upload_url_returns_target(client, db_pool, study_root):
    from app.services import storage as svc
    result = await svc.signed_upload_url("ASB/upload.pdf")
    assert result["path"] == "ASB/upload.pdf"
    assert result["url"].startswith("/api/files/upload-target?path=")
    assert "upload.pdf" in result["url"]


# ── _log course-code extraction (Batch A behaviour preserved) ────────────────


async def _seed_course(db_pool, code: str) -> None:
    """Insert a courses row so the events FK is satisfied."""
    async with db_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "INSERT INTO courses (code, full_name) VALUES (%s, %s) "
            "ON CONFLICT DO NOTHING",
            (code, f"Test course {code}"),
        )


@pytest.mark.asyncio
async def test_log_populates_course_code_from_path(client, db_pool, study_root):
    """Uploads under a recognisable course folder log events with course_code set."""
    from app.services import storage as svc
    await _seed_course(db_pool, "ASB")
    await svc.upload("ASB/lecture.pdf", b"x")

    async with db_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT course_code, payload FROM events "
            "WHERE kind = 'storage:upload' "
            "AND payload->>'path' = 'ASB/lecture.pdf' "
            "ORDER BY created_at DESC LIMIT 1"
        )
        row = await cur.fetchone()
    assert row is not None
    assert row["course_code"] == "ASB"


@pytest.mark.asyncio
async def test_log_skips_course_code_for_top_level_files(client, db_pool, study_root):
    """A file at the root has no leading folder → course_code stays NULL."""
    from app.services import storage as svc
    await svc.upload("just_a_file.txt", b"x")

    async with db_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT course_code FROM events "
            "WHERE kind = 'storage:upload' "
            "AND payload->>'path' = 'just_a_file.txt' "
            "ORDER BY created_at DESC LIMIT 1"
        )
        row = await cur.fetchone()
    assert row is not None
    assert row["course_code"] is None


@pytest.mark.asyncio
async def test_log_uses_paths_array_for_delete(client, db_pool, study_root):
    """`delete()` payload uses `paths: [...]` — _log() picks the first entry."""
    from app.services import storage as svc
    await _seed_course(db_pool, "EXAM")
    (study_root / "EXAM").mkdir()
    (study_root / "EXAM" / "x.txt").write_bytes(b"y")
    await svc.delete(["EXAM/x.txt"])

    async with db_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT course_code FROM events "
            "WHERE kind = 'storage:delete' "
            "ORDER BY created_at DESC LIMIT 1"
        )
        row = await cur.fetchone()
    assert row is not None
    assert row["course_code"] == "EXAM"
