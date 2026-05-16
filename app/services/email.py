"""Pluggable email service.

Backends
--------
console    — default; captures sends to _console_outbox for test inspection.
gmail_smtp — stdlib smtplib.SMTP_SSL to smtp.gmail.com:465.

Backend selection: EMAIL_BACKEND env var (default "console").
"""
import asyncio
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path
from typing import Awaitable, Callable

from jinja2 import Environment, FileSystemLoader, TemplateNotFound

from app.config import get_settings

# ── Jinja2 environment ────────────────────────────────────────────────────────

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates" / "email"

_jinja_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=False,
)

# ── Console backend ───────────────────────────────────────────────────────────

_console_outbox: list[dict] = []


def reset_console_outbox() -> None:
    """Clear the in-memory outbox (call at the start of each test)."""
    _console_outbox.clear()


async def _console_backend(
    *,
    to: str,
    subject: str,
    body_text: str,
    body_html: str | None,
    from_addr: str,
    from_name: str,
) -> None:
    record = {
        "to": to,
        "subject": subject,
        "body_text": body_text,
        "body_html": body_html,
        "from_addr": from_addr,
        "from_name": from_name,
    }
    _console_outbox.append(record)
    print(
        f"[email:console] to={to!r} subject={subject!r} "
        f"text_len={len(body_text)} html={'yes' if body_html else 'no'}"
    )


# ── Gmail SMTP backend ────────────────────────────────────────────────────────


async def _gmail_smtp_backend(
    *,
    to: str,
    subject: str,
    body_text: str,
    body_html: str | None,
    from_addr: str,
    from_name: str,
) -> None:
    settings = get_settings()
    user = settings.gmail_smtp_user
    password = settings.gmail_smtp_app_password

    msg = EmailMessage()
    msg["From"] = f"{from_name} <{from_addr}>"
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body_text)
    if body_html:
        msg.add_alternative(body_html, subtype="html")

    ctx = ssl.create_default_context()

    def _send() -> None:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ctx) as smtp:
            smtp.login(user, password)
            smtp.send_message(msg)

    # Run the blocking smtplib call in a thread pool to avoid blocking the
    # asyncio event loop.
    await asyncio.get_event_loop().run_in_executor(None, _send)


# ── Backend registry ──────────────────────────────────────────────────────────

EmailBackend = Callable[..., Awaitable[None]]

_BACKENDS: dict[str, EmailBackend] = {
    "console": _console_backend,
    "gmail_smtp": _gmail_smtp_backend,
}


def _get_backend() -> EmailBackend:
    settings = get_settings()
    name = settings.email_backend
    backend = _BACKENDS.get(name)
    if backend is None:
        raise ValueError(
            f"Unknown EMAIL_BACKEND={name!r}. "
            f"Valid options: {list(_BACKENDS)}"
        )
    return backend


# ── Public API ────────────────────────────────────────────────────────────────


async def send_email(
    *,
    to: str,
    subject: str,
    body_text: str,
    body_html: str | None = None,
) -> None:
    """Dispatch an email to the configured backend."""
    settings = get_settings()
    backend = _get_backend()
    await backend(
        to=to,
        subject=subject,
        body_text=body_text,
        body_html=body_html,
        from_addr=settings.email_from,
        from_name=settings.email_from_name,
    )


def render(template_name: str, context: dict) -> tuple[str, str]:
    """Render a (txt, html) pair from app/templates/email/<name>.{txt,html}.j2.

    Raises TemplateNotFound if either template file is missing.
    """
    try:
        txt = _jinja_env.get_template(f"{template_name}.txt.j2").render(**context)
    except TemplateNotFound:
        raise TemplateNotFound(f"{template_name}.txt.j2")

    try:
        html = _jinja_env.get_template(f"{template_name}.html.j2").render(**context)
    except TemplateNotFound:
        raise TemplateNotFound(f"{template_name}.html.j2")

    return txt, html
