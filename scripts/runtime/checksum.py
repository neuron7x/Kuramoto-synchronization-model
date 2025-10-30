"""Checksum helpers for verifying downloaded artefacts."""

from __future__ import annotations

# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
import hashlib
from pathlib import Path

_BUFFER_SIZE = 1024 * 1024


class ChecksumMismatchError(RuntimeError):
    """Raised when a computed checksum does not match the expected value."""


def compute_checksum(path: Path | str, *, algorithm: str = "sha256") -> str:
    """Compute the checksum for *path* using the provided hash *algorithm*."""

    hasher = hashlib.new(algorithm)
    with Path(path).open("rb") as handle:
        while True:
            chunk = handle.read(_BUFFER_SIZE)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def verify_checksum(
    path: Path | str, expected: str, *, algorithm: str = "sha256"
) -> None:
    """Raise :class:`ChecksumMismatchError` if the checksum differs from *expected*."""

    actual = compute_checksum(path, algorithm=algorithm)
    if actual.lower() != expected.lower():
        raise ChecksumMismatchError(
            f"Checksum mismatch for {path!s}: expected {expected}, computed {actual}"
        )
