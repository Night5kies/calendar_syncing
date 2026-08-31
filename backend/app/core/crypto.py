"""Symmetric encryption for provider secrets held at rest.

`calendar_connections.access_token` / `refresh_token` are long-lived Google
credentials. They are encrypted with a Fernet key from
`settings.token_encryption_key` before they reach the database.

Ciphertext is tagged with `ENCRYPTION_PREFIX` so `decrypt_secret` can tell an
encrypted value from a legacy plaintext one and read both. That makes the
rollout a no-op for rows written before this landed: they decrypt as
themselves and are re-encrypted the next time they are written.
"""
from __future__ import annotations

import logging

from app.core.config import settings

logger = logging.getLogger(__name__)

ENCRYPTION_PREFIX = "enc:v1:"

_warned_missing_key = False


def _fernet():
    """Return a Fernet instance, or None when no key is configured."""
    key = settings.token_encryption_key
    if not key:
        return None
    from cryptography.fernet import Fernet

    return Fernet(key.encode() if isinstance(key, str) else key)


def _warn_once() -> None:
    global _warned_missing_key
    if _warned_missing_key:
        return
    _warned_missing_key = True
    if settings.env != "local":
        logger.warning(
            "TOKEN_ENCRYPTION_KEY is not set; provider OAuth tokens are being "
            "stored as plaintext. Set it before running in production."
        )


def encrypt_secret(value: str | None) -> str | None:
    if value is None:
        return None
    if value.startswith(ENCRYPTION_PREFIX):
        return value
    fernet = _fernet()
    if fernet is None:
        _warn_once()
        return value
    return ENCRYPTION_PREFIX + fernet.encrypt(value.encode()).decode()


def decrypt_secret(value: str | None) -> str | None:
    if value is None:
        return None
    if not value.startswith(ENCRYPTION_PREFIX):
        # Legacy row written before encryption was enabled.
        return value
    fernet = _fernet()
    if fernet is None:
        logger.error(
            "Found an encrypted provider token but TOKEN_ENCRYPTION_KEY is not "
            "set; the connection cannot be used until the key is restored."
        )
        return None
    from cryptography.fernet import InvalidToken

    try:
        return fernet.decrypt(value[len(ENCRYPTION_PREFIX) :].encode()).decode()
    except InvalidToken:
        logger.error("Provider token failed to decrypt (wrong TOKEN_ENCRYPTION_KEY?)")
        return None


def generate_key() -> str:
    """Convenience for operators: `python -c "from app.core.crypto import generate_key; print(generate_key())"`."""
    from cryptography.fernet import Fernet

    return Fernet.generate_key().decode()
