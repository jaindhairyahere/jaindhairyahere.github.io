"""Application-level field encryption for sensitive card data.

Uses Fernet (AES-128-CBC + HMAC) with the key from ``FIELD_ENCRYPTION_KEY``.
Values are encrypted at rest and only ever decrypted for the owner. Never
expose decrypted values in list serializers or logs.
"""
from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import models


def _fernet():
    from cryptography.fernet import Fernet

    key = settings.FIELD_ENCRYPTION_KEY
    if not key or key == "change-me-generate-a-fernet-key":
        raise ImproperlyConfigured(
            "FIELD_ENCRYPTION_KEY is not set. Generate one with: "
            "python -c \"from cryptography.fernet import Fernet;"
            "print(Fernet.generate_key().decode())\""
        )
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt(value: str | None) -> str | None:
    if value is None or value == "":
        return value
    return _fernet().encrypt(value.encode()).decode()


def decrypt(token: str | None) -> str | None:
    if token is None or token == "":
        return token
    from cryptography.fernet import InvalidToken

    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        return None


class EncryptedCharField(models.TextField):
    """A TextField that transparently encrypts/decrypts its value.

    Stored ciphertext is opaque; the plaintext is only materialized in Python.
    Not queryable by value (by design — it is secret).
    """

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        return encrypt(value)

    def from_db_value(self, value, expression, connection):
        return decrypt(value)

    def to_python(self, value):
        return value
