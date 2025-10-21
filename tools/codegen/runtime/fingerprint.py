from __future__ import annotations

"""Hash utilities used to guarantee deterministic code generation."""

import hashlib
from pathlib import Path
from typing import Iterable


def stable_hash(parts: Iterable[str | bytes]) -> str:
    """Compute a deterministic sha256 hash for the provided parts."""

    digest = hashlib.sha256()
    for part in parts:
        if isinstance(part, str):
            digest.update(part.encode("utf-8"))
        else:
            digest.update(part)
    return digest.hexdigest()


def file_fingerprint(path: Path) -> str:
    """Fingerprint the contents of a file."""

    return stable_hash([path.read_text(encoding="utf-8")])
