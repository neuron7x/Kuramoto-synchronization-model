"""Utilities for authenticated encryption between internal components."""

from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

__all__ = ["SecureEnvelope", "SecureChannel", "EncryptedPayload"]


def _derive_key(material: bytes, *, salt: bytes | None = None) -> bytes:
    if not material:
        raise ValueError("key material must not be empty")
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        info=b"tradepulse.secure_channel",
    )
    return hkdf.derive(material)


@dataclass(slots=True)
class EncryptedPayload:
    nonce: str
    ciphertext: str
    associated_data: str | None = None

    def to_json(self) -> str:
        return json.dumps(self.__dict__)

    @classmethod
    def from_json(cls, data: str) -> "EncryptedPayload":
        payload = json.loads(data)
        return cls(**payload)


class SecureEnvelope:
    """Perform authenticated encryption with modern AEAD primitives."""

    def __init__(self, key_material: bytes, *, salt: bytes | None = None) -> None:
        self._key = _derive_key(key_material, salt=salt)
        self._aead = AESGCM(self._key)

    def encrypt(
        self,
        plaintext: bytes,
        *,
        associated_data: bytes | None = None,
    ) -> EncryptedPayload:
        nonce = os.urandom(12)
        ciphertext = self._aead.encrypt(nonce, plaintext, associated_data)
        return EncryptedPayload(
            nonce=base64.b64encode(nonce).decode("ascii"),
            ciphertext=base64.b64encode(ciphertext).decode("ascii"),
            associated_data=(
                base64.b64encode(associated_data).decode("ascii")
                if associated_data
                else None
            ),
        )

    def decrypt(self, payload: EncryptedPayload) -> bytes:
        nonce = base64.b64decode(payload.nonce)
        ciphertext = base64.b64decode(payload.ciphertext)
        aad = (
            base64.b64decode(payload.associated_data)
            if payload.associated_data is not None
            else None
        )
        return self._aead.decrypt(nonce, ciphertext, aad)


class SecureChannel:
    """Coordinate encryption using secrets sourced at runtime."""

    def __init__(self, secret_provider: Callable[[], str]) -> None:
        if not callable(secret_provider):
            raise ValueError("secret_provider must be callable")
        self._secret_provider = secret_provider

    def wrap_json(
        self,
        payload: Mapping[str, Any],
        *,
        associated_data: Mapping[str, Any] | None = None,
    ) -> EncryptedPayload:
        envelope = self._build_envelope(associated_data)
        plaintext = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        aad_bytes = (
            json.dumps(associated_data, separators=(",", ":")).encode("utf-8")
            if associated_data is not None
            else None
        )
        return envelope.encrypt(plaintext, associated_data=aad_bytes)

    def unwrap_json(
        self,
        payload: EncryptedPayload,
        *,
        associated_data: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]:
        envelope = self._build_envelope(associated_data)
        aad_bytes = (
            json.dumps(associated_data, separators=(",", ":")).encode("utf-8")
            if associated_data is not None
            else None
        )
        try:
            plaintext = envelope.decrypt(payload)
        except InvalidTag as exc:
            raise ValueError("Failed to decrypt payload") from exc
        if aad_bytes is not None:
            # Ensure the caller-provided associated data matches the encrypted payload.
            encoded = base64.b64encode(aad_bytes).decode("ascii")
            if payload.associated_data != encoded:
                raise ValueError("Associated data mismatch")
        return json.loads(plaintext.decode("utf-8"))

    def _build_envelope(
        self, associated_data: Mapping[str, Any] | None
    ) -> SecureEnvelope:
        secret = self._secret_provider()
        if not secret:
            raise ValueError("secret_provider returned empty secret")
        salt = None
        if associated_data is not None:
            salt = json.dumps(associated_data, separators=(",", ":")).encode("utf-8")
        return SecureEnvelope(secret.encode("utf-8"), salt=salt)
