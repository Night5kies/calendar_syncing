"""Custom SQLAlchemy column types."""
from __future__ import annotations

from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator

from app.core.crypto import decrypt_secret, encrypt_secret


class EncryptedText(TypeDecorator):
    """Text column whose value is encrypted on the way to the database.

    Application code reads and writes plaintext; only the stored value is
    ciphertext. See `app.core.crypto` for the key handling and the
    plaintext-passthrough behaviour for rows written before encryption.
    """

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):  # noqa: D102 - SQLAlchemy hook
        return encrypt_secret(value)

    def process_result_value(self, value, dialect):  # noqa: D102 - SQLAlchemy hook
        return decrypt_secret(value)
