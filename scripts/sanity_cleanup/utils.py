"""Shared helper utilities for sanity cleanup tasks."""

from __future__ import annotations

# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
import hashlib
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]


def safe_relpath(path: Path, start: Path | None = None) -> str:
    """Return a repository-relative path when possible."""

    base = (start or _REPO_ROOT).resolve()
    try:
        return str(path.resolve().relative_to(base))
    except ValueError:
        return str(path.resolve())


def format_path(path: Path) -> str:
    """Return a deterministic string representation for *path*."""

    return safe_relpath(path)


def sha256sum(path: Path, *, chunk_size: int = 65536) -> str:
    """Compute the SHA-256 digest for *path* using streaming IO."""

    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            hasher.update(chunk)
    return hasher.hexdigest()
