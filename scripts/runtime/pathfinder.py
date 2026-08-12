# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Utilities for locating input resources across different environments."""

from __future__ import annotations

# SPDX-License-Identifier: MIT
from pathlib import Path
from typing import Iterable, Iterator, Sequence


def _iter_roots(roots: Sequence[str | Path] | None) -> Iterable[Path]:
    if not roots:
        yield Path.cwd()
        return
    for raw in roots:
        path = Path(raw).expanduser()
        if not path.exists():
            continue
        yield path


def find_resources(pattern: str, roots: Sequence[str | Path] | None = None) -> Iterator[Path]:
    """Yield files matching *pattern* using :meth:`Path.rglob` for robustness."""

    seen: set[Path] = set()
    for root in _iter_roots(roots):
        for candidate in root.rglob(pattern):
            try:
                resolved = candidate.resolve()
            except OSError:
                continue
            if resolved in seen:
                continue
            seen.add(resolved)
            yield resolved
