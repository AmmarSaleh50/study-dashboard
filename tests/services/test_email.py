"""Tests for app/services/email.py — console + gmail_smtp backends."""
import pytest


@pytest.mark.asyncio
async def test_console_backend_captures_send(monkeypatch):
    monkeypatch.setenv("EMAIL_BACKEND", "console")
    from app.config import get_settings; get_settings.cache_clear()
    from app.services import email as svc
    svc.reset_console_outbox()
    await svc.send_email(to="x@y.test", subject="hi", body_text="hello", body_html="<p>hello</p>")
    assert len(svc._console_outbox) == 1
    sent = svc._console_outbox[0]
    assert sent["to"] == "x@y.test"
    assert sent["subject"] == "hi"
    assert "hello" in sent["body_text"]


def test_render_returns_txt_and_html(tmp_path):
    from app.services import email as svc
    txt, html = svc.render("hello", {"name": "Ammar"})
    # Templates use Jinja2 syntax — assert basic substitution worked
    assert "Ammar" in txt
    assert "Ammar" in html


@pytest.mark.asyncio
async def test_gmail_smtp_backend_uses_smtplib(monkeypatch):
    """Mock smtplib and assert backend calls SMTP_SSL with the right host + creds."""
    captured = {}
    class MockSMTP:
        def __init__(self, host, port, context=None): captured["host"] = host; captured["port"] = port
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def login(self, user, password): captured["user"] = user; captured["password"] = password
        def send_message(self, msg): captured["msg"] = msg
    monkeypatch.setattr("smtplib.SMTP_SSL", MockSMTP)
    monkeypatch.setenv("EMAIL_BACKEND", "gmail_smtp")
    monkeypatch.setenv("GMAIL_SMTP_USER", "test@gmail.test")
    monkeypatch.setenv("GMAIL_SMTP_APP_PASSWORD", "abcd efgh ijkl mnop")
    monkeypatch.setenv("EMAIL_FROM", "hello@openstudy.dev")
    monkeypatch.setenv("EMAIL_FROM_NAME", "OpenStudy")
    from app.config import get_settings; get_settings.cache_clear()
    from app.services import email as svc
    await svc.send_email(to="x@y.test", subject="hi", body_text="hello", body_html=None)
    assert captured["host"] == "smtp.gmail.com"
    assert captured["port"] == 465
    assert captured["user"] == "test@gmail.test"
