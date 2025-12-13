"""Symmetric encryption utilities."""

from __future__ import annotations

import base64
import os

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


class Encryption:
    """Fernet-based encryption with PBKDF2 key derivation."""

    def __init__(self) -> None:
        key_material = os.getenv("ENCRYPTION_KEY")
        if not key_material:
            raise ValueError("ENCRYPTION_KEY environment variable must be set")
        salt_value = os.getenv("ENCRYPTION_SALT")
        if not salt_value:
            raise ValueError("ENCRYPTION_SALT environment variable must be set")
        salt = salt_value.encode()
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=480000,
        )
        derived = kdf.derive(key_material.encode())
        self.fernet = Fernet(base64.urlsafe_b64encode(derived))

    def encrypt(self, data: bytes) -> bytes:
        """Encrypt data bytes."""

        return self.fernet.encrypt(data)

    def decrypt(self, data: bytes) -> bytes:
        """Decrypt data bytes."""

        return self.fernet.decrypt(data)


class EncryptedField:
    """Helper to encrypt/decrypt string fields."""

    def __init__(self) -> None:
        self.cipher = Encryption()

    def encrypt_value(self, value: str) -> str:
        token = self.cipher.encrypt(value.encode())
        return base64.b64encode(token).decode()

    def decrypt_value(self, value: str) -> str:
        raw = base64.b64decode(value.encode())
        return self.cipher.decrypt(raw).decode()
