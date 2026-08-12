# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Vault-backed secret retrieval and transit helpers."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

try:  # Optional dependency
    import hvac
except ImportError:  # pragma: no cover - handled at runtime
    hvac = None  # type: ignore[assignment]


class Secrets:
    """Thin wrapper around HashiCorp Vault KV and transit engines."""

    def __init__(self, client: Any | None = None) -> None:
        if client is not None:
            self.vault = client
        else:
            if hvac is None:
                raise ImportError("hvac must be installed to use Secrets without a custom client")
            self.vault = hvac.Client(
                url=os.getenv("VAULT_ADDR"),
                token=os.getenv("VAULT_TOKEN"),
            )

    @lru_cache(maxsize=128)
    def get(self, path: str) -> dict[str, Any]:
        """Retrieve a KV secret version."""

        data: dict[str, Any] = self.vault.secrets.kv.v2.read_secret_version(path=path)["data"][
            "data"
        ]
        return data

    def encrypt(self, data: str) -> str:
        """Encrypt plaintext using the transit engine."""

        ciphertext: str = self.vault.secrets.transit.encrypt_data(
            name="geosync-master",
            plaintext=data,
        )["data"]["ciphertext"]
        return ciphertext

    def decrypt(self, cipher: str) -> str:
        """Decrypt a transit ciphertext."""

        plaintext: str = self.vault.secrets.transit.decrypt_data(
            name="geosync-master",
            ciphertext=cipher,
        )["data"]["plaintext"]
        return plaintext


secrets: Secrets | None
try:
    secrets = Secrets()
except (ImportError, ValueError):
    # Optional default instance; consumers can instantiate with explicit client.
    secrets = None
