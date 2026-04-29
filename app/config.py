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

    # PostgREST (the data-plane HTTP layer in front of Postgres).
    postgrest_url: str = Field(default="")
    postgrest_api_key: str = Field(default="")
    # When true (default), send `apikey` + `Authorization: Bearer …` to
    # PostgREST — required when PostgREST validates JWTs. Set to false when
    # JWT auth is disabled on the PostgREST side; otherwise a non-JWT
    # bearer value triggers a 500.
    postgrest_auth: bool = Field(default=True)

    # Auth
    app_password_hash: str = Field(default="")
    # No default — production deploys must set SESSION_SECRET. The setter
    # below raises if it's left empty so we fail-closed instead of signing
    # cookies with a publicly-known string.
    session_secret: str = Field(default="")
    session_ttl_days: int = 30

    # Public origin (scheme+host, no trailing slash) — required for OAuth/MCP URLs.
    # In prod, set to your public origin (e.g. https://openstudy.dev).
    public_url: str = ""

    # CORS — comma-separated
    cors_origins: str = "http://localhost:5173,http://localhost:5174"

    # Rate limit
    login_attempts_window_min: int = 10
    login_attempts_max: int = 5

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
