"""Versioned authenticated encryption for uploaded CV documents."""

from __future__ import annotations

import base64
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MAGIC = b"TASKSNIFFER-CV\x01"
NONCE_SIZE = 12
KEY_SIZE = 32


class CVEncryptionError(ValueError):
    """Base class for safe CV encryption/decryption failures."""


class LegacyPlaintextCVError(CVEncryptionError):
    """Raised when a stored CV has not yet been migrated to encrypted form."""


def is_encrypted_cv(stored: bytes) -> bool:
    return stored.startswith(MAGIC)


def load_cv_key(encoded_key: str) -> bytes:
    if not encoded_key:
        raise CVEncryptionError("CV encryption key is not configured")
    try:
        key = base64.b64decode(encoded_key.encode("ascii"), altchars=b"-_", validate=True)
    except (ValueError, UnicodeError) as exc:
        raise CVEncryptionError("CV encryption key must be URL-safe base64") from exc
    if len(key) != KEY_SIZE:
        raise CVEncryptionError("CV encryption key must decode to exactly 32 bytes")
    return key


def encrypt_cv(plaintext: bytes, encoded_key: str) -> bytes:
    if plaintext.startswith(MAGIC):
        raise CVEncryptionError("Refusing to encrypt an already encrypted CV")
    nonce = os.urandom(NONCE_SIZE)
    return MAGIC + nonce + AESGCM(load_cv_key(encoded_key)).encrypt(nonce, plaintext, MAGIC)


def decrypt_cv(stored: bytes, encoded_key: str) -> bytes:
    if not stored.startswith(MAGIC):
        raise LegacyPlaintextCVError("CV requires the legacy-file encryption migration")
    start = len(MAGIC)
    if len(stored) < start + NONCE_SIZE + 16:
        raise CVEncryptionError("Stored CV ciphertext is truncated")
    nonce = stored[start : start + NONCE_SIZE]
    ciphertext = stored[start + NONCE_SIZE :]
    try:
        return AESGCM(load_cv_key(encoded_key)).decrypt(nonce, ciphertext, MAGIC)
    except InvalidTag as exc:
        raise CVEncryptionError("Stored CV authentication failed") from exc
