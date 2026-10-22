"""Authenticated CV encryption format and key validation tests."""

import base64

import pytest

from backend.security.cv_encryption import (
    CVEncryptionError,
    LegacyPlaintextCVError,
    decrypt_cv,
    encrypt_cv,
)


KEY = base64.urlsafe_b64encode(b"test-key-material-32-bytes-long!!"[:32]).decode()


def test_cv_encryption_round_trip_uses_unique_nonces():
    one = encrypt_cv(b"private cv bytes", KEY)
    two = encrypt_cv(b"private cv bytes", KEY)
    assert one != two
    assert decrypt_cv(one, KEY) == b"private cv bytes"
    assert decrypt_cv(two, KEY) == b"private cv bytes"


def test_invalid_key_and_wrong_key_fail_closed():
    with pytest.raises(CVEncryptionError):
        encrypt_cv(b"private", "not-a-32-byte-key")
    ciphertext = encrypt_cv(b"private", KEY)
    wrong_key = base64.urlsafe_b64encode(b"x" * 32).decode()
    with pytest.raises(CVEncryptionError):
        decrypt_cv(ciphertext, wrong_key)


def test_corrupted_or_legacy_file_is_not_returned_as_plaintext():
    ciphertext = bytearray(encrypt_cv(b"private", KEY))
    ciphertext[-1] ^= 1
    with pytest.raises(CVEncryptionError):
        decrypt_cv(bytes(ciphertext), KEY)
    with pytest.raises(LegacyPlaintextCVError):
        decrypt_cv(b"old plaintext CV", KEY)


def test_encrypt_refuses_to_double_encrypt():
    ciphertext = encrypt_cv(b"private", KEY)
    with pytest.raises(CVEncryptionError):
        encrypt_cv(ciphertext, KEY)
