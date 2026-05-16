from functools import lru_cache
from typing import List
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Auth
    app_password_hash: str = Field(default="")
    # No default — production deploys must set SESSION_SECRET. The setter
    # below raises if it's left empty so we fail-closed instead of signing
    # cookies with a publicly-known string.
    session_secret: str = Field(default="")

    # Operator identity — Phase 1+. Defaults match the seed row created by
    # the users-table migration. Self-hosters can override these — but if you
    # do, also UPDATE the users row in DB to match (or wait for Phase 3's
    # signup endpoints).
    operator_user_id: str = Field(
        default="00000000-0000-0000-0000-000000000001",
        description="UUID of the operator user (matches users.id row in DB).",
    )
    operator_email: str = Field(
        default="operator@local",
        description="Email of the operator user (matches users.email).",
    )
    operator_display_name: str = Field(
        default="Operator",
        description="Display name of the operator user.",
    )
    session_ttl_days: int = 30

    # Expose FastAPI's auto-generated /api/docs (Swagger UI) + /api/openapi.json.
    # Default OFF — they're recon assist for attackers. Set EXPOSE_DOCS=true
    # in dev .env if you want them. Production should always be false.
    expose_docs: bool = False

    # Public origin (scheme+host, no trailing slash) — required for OAuth/MCP URLs.
    # In prod, set to your public origin (e.g. https://openstudy.dev).
    public_url: str = ""

    # CORS — comma-separated
    cors_origins: str = "http://localhost:5173,http://localhost:5174"

    # Rate limit
    login_attempts_window_min: int = 10
    login_attempts_max: int = 5

    secrets_encryption_key: str = Field(default="", description="Fernet master key (mint with cryptography.fernet.Fernet.generate_key())")

    # Email — Phase 3+
    email_backend: str = Field(default="console", description="Email backend: console|gmail_smtp")
    gmail_smtp_user: str = Field(default="", description="Gmail SMTP username (your gmail address)")
    gmail_smtp_app_password: str = Field(default="", description="Gmail app-password (16 chars, no spaces in storage)")
    email_from: str = Field(default="hello@openstudy.dev", description="From: address for outbound emails")
    email_from_name: str = Field(default="OpenStudy", description="From: name")

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.session_secret or self.session_secret == "dev-only-change-me":
            raise RuntimeError(
                "SESSION_SECRET is unset or still the placeholder. "
                "Generate one with: python -c 'import secrets; "
                "print(secrets.token_urlsafe(48))'"
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()
