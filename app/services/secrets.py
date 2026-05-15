"""Symmetric encryption for at-rest secrets.

Used by Phase 6 for per-user Telegram/Moodle credentials. Phase 0 ships
the helpers and a unit test so the env var is in place on every deploy
before the first encrypted column lands.

Master key: env var SECRETS_ENCRYPTION_KEY (Fernet.generate_key() output).
Rotation: switch to MultiFernet with SECRETS_ENCRYPTION_KEYS later — out
of scope for Phase 0.
"""
from cryptography.fernet import Fernet

from ..config import get_settings


def _fernet() -> Fernet:
    key = get_settings().secrets_encryption_key
    if not key:
        raise RuntimeError(
            "SECRETS_ENCRYPTION_KEY is not set; mint one with "
            "`python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'`"
        )
    return Fernet(key.encode())


def encrypt(plain: str) -> bytes:
    return _fernet().encrypt(plain.encode("utf-8"))


def decrypt(token: bytes) -> str:
    return _fernet().decrypt(token).decode("utf-8")
