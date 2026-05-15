import os
import pytest
from cryptography.fernet import Fernet


def test_encrypt_decrypt_roundtrip(monkeypatch):
    monkeypatch.setenv("SECRETS_ENCRYPTION_KEY", Fernet.generate_key().decode())
    from app.config import get_settings
    get_settings.cache_clear()
    from app.services import secrets as svc
    ct = svc.encrypt("hello world")
    assert isinstance(ct, bytes)
    assert svc.decrypt(ct) == "hello world"


def test_missing_key_raises(monkeypatch):
    monkeypatch.setenv("SECRETS_ENCRYPTION_KEY", "")
    from app.config import get_settings
    get_settings.cache_clear()
    from app.services import secrets as svc
    with pytest.raises(RuntimeError, match="SECRETS_ENCRYPTION_KEY"):
        svc.encrypt("anything")


def test_decrypt_invalid_ciphertext_raises(monkeypatch):
    monkeypatch.setenv("SECRETS_ENCRYPTION_KEY", Fernet.generate_key().decode())
    from app.config import get_settings
    get_settings.cache_clear()
    from app.services import secrets as svc
    with pytest.raises(Exception):
        svc.decrypt(b"not-a-fernet-token")
