"""MCP tool tests — course files + notify_telegram (3 tools, 7 tests).

Coverage: list_course_files, read_course_file, notify_telegram.

`list_course_files` and `read_course_file` are filesystem-backed via
`app.services.storage` — point `STUDY_ROOT` at a per-test `tmp_path` and
write fixtures to disk directly. `notify_telegram` is sync and HTTP-backed,
so we monkeypatch `httpx.post` for the success path.
"""
import pytest

from tests.mcp._harness import get_tool_fn


@pytest.fixture
def study_root(tmp_path, monkeypatch):
    """Point STUDY_ROOT at a per-test directory and pre-create the sentinel
    user's subdir. After Phase 2, storage operations resolve under
    `STUDY_ROOT/<user_id>/`; the MCP tools pass SENTINEL_USER_ID, so the
    files must land in that subdir for the tools to see them."""
    from app.auth import SENTINEL_USER_ID
    monkeypatch.setenv("STUDY_ROOT", str(tmp_path))
    user_dir = tmp_path / str(SENTINEL_USER_ID)
    user_dir.mkdir(parents=True, exist_ok=True)
    return user_dir


# ── list_course_files ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_course_files_empty(client, db_conn, mcp_server, study_root):
    """Listing under a missing course folder returns an empty list."""
    list_course_files = get_tool_fn(mcp_server, "list_course_files")
    result = await list_course_files(prefix="MCPF1")
    assert result == []


@pytest.mark.asyncio
async def test_list_course_files_after_upload(client, db_conn, mcp_server, study_root):
    """A file dropped on disk shows up in the listing with type='file' and matching path."""
    list_course_files = get_tool_fn(mcp_server, "list_course_files")

    course_dir = study_root / "MCPF1"
    course_dir.mkdir()
    (course_dir / "notes.md").write_text("# notes", encoding="utf-8")

    result = await list_course_files(prefix="MCPF1")
    assert len(result) == 1
    entry = result[0]
    assert entry["name"] == "notes.md"
    assert entry["path"] == "MCPF1/notes.md"
    assert entry["type"] == "file"


# ── read_course_file ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_read_text_file(client, db_conn, mcp_server, study_root):
    """Reading a `.md` file returns its decoded text as the only list item."""
    read_course_file = get_tool_fn(mcp_server, "read_course_file")

    course_dir = study_root / "MCPF1"
    course_dir.mkdir()
    body = "# Notes\nhello world\n"
    # write_bytes (not write_text) to avoid Windows CRLF translation.
    (course_dir / "notes.md").write_bytes(body.encode("utf-8"))

    result = await read_course_file(path="MCPF1/notes.md")
    assert result == [body]


@pytest.mark.asyncio
async def test_read_missing_file_raises_or_returns_error(
    client, db_conn, mcp_server, study_root
):
    """Reading a nonexistent path either raises or returns an error-shaped dict."""
    read_course_file = get_tool_fn(mcp_server, "read_course_file")

    try:
        result = await read_course_file(path="MCPF1/nope.md")
    except Exception as exc:
        assert "not found" in str(exc).lower() or isinstance(exc, FileNotFoundError)
        return
    # If it didn't raise, accept None / empty / error-shaped response.
    assert (
        result is None
        or result == []
        or (isinstance(result, dict) and not result.get("ok", True))
    )


@pytest.mark.asyncio
async def test_read_pdf_with_page_range(client, db_conn, mcp_server, study_root):
    """A 1-page PDF with `pages='1'` returns one rendered-page item.

    The tool returns MCPImage objects for PDFs (not text); assert len + truthiness.
    """
    import fitz  # pymupdf

    read_course_file = get_tool_fn(mcp_server, "read_course_file")

    course_dir = study_root / "MCPF1"
    course_dir.mkdir()
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "hello pdf")
    pdf_bytes = doc.tobytes()
    doc.close()
    (course_dir / "slides.pdf").write_bytes(pdf_bytes)

    result = await read_course_file(path="MCPF1/slides.pdf", pages="1")
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0] is not None


# ── notify_telegram ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_notify_telegram_missing_env_returns_error(
    client, db_conn, mcp_server, monkeypatch
):
    """Without TELEGRAM_BOT_TOKEN/CHAT_ID set, the tool returns ok=False with an error."""
    notify_telegram = get_tool_fn(mcp_server, "notify_telegram")
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    result = notify_telegram(text="hi")
    assert isinstance(result, dict)
    assert result.get("ok") is False
    assert "error" in result


@pytest.mark.asyncio
async def test_notify_telegram_success_with_mocked_httpx(
    client, db_conn, mcp_server, monkeypatch
):
    """With env set + httpx.post mocked to return ok=True, the tool returns the message_id.

    `httpx` is imported inside the function body, so monkeypatching the module
    attribute (`httpx.post`) is enough — the function picks up the patched
    callable when it does `import httpx` at call time.
    """
    import httpx

    notify_telegram = get_tool_fn(mcp_server, "notify_telegram")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")

    class _FakeResponse:
        def json(self):
            return {"ok": True, "result": {"message_id": 42}}

    def _fake_post(url, json=None, timeout=None):  # noqa: A002 (shadow `json` like httpx)
        assert "api.telegram.org" in url
        assert json["chat_id"] == 12345
        assert json["text"] == "hello"
        return _FakeResponse()

    monkeypatch.setattr(httpx, "post", _fake_post)

    result = notify_telegram(text="hello")
    assert result == {"ok": True, "message_id": 42}
