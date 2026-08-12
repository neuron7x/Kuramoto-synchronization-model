# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Utilities for constraining filesystem access to safe locations."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Iterable


class DataPathGuard:
    """Validate and normalise filesystem paths for data ingestion."""

    _DEFAULT_MAX_BYTES = 50 * 1024 * 1024  # 50 MiB

    def __init__(
        self,
        allowed_roots: Iterable[str | Path] | None = None,
        *,
        max_bytes: int | None = None,
        follow_symlinks: bool = False,
    ) -> None:
        env_roots = os.environ.get("GEOSYNC_DATA_ROOTS")
        roots: list[str | Path] = []

        if env_roots:
            roots.extend(part for part in env_roots.split(os.pathsep) if part)

        if allowed_roots is not None:
            roots.extend(allowed_roots)

        if not roots:
            roots.extend([Path.cwd(), Path(tempfile.gettempdir())])

        resolved_roots: list[Path] = []
        for entry in roots:
            root = Path(entry).expanduser().resolve(strict=False)
            if not root.exists():
                raise FileNotFoundError(f"Allowed data root does not exist: {root}")
            if not root.is_dir():
                raise NotADirectoryError(
                    f"Allowed data root is not a directory: {root}"
                )
            resolved_roots.append(root)

        if not resolved_roots:
            raise ValueError("At least one allowed data root must be configured")

        self._allowed_roots: tuple[Path, ...] = tuple(dict.fromkeys(resolved_roots))
        self._follow_symlinks = follow_symlinks

        if max_bytes is None:
            max_bytes_env = os.environ.get("GEOSYNC_MAX_CSV_BYTES")
            if max_bytes_env:
                try:
                    max_bytes = int(max_bytes_env)
                except ValueError as exc:  # pragma: no cover - defensive
                    raise ValueError(
                        "GEOSYNC_MAX_CSV_BYTES must be an integer"
                    ) from exc
            else:
                max_bytes = self._DEFAULT_MAX_BYTES

        if max_bytes <= 0:
            raise ValueError("Maximum allowed file size must be a positive integer")

        self._max_bytes = int(max_bytes)

    @property
    def allowed_roots(self) -> tuple[Path, ...]:
        """Return the configured allowed roots."""

        return self._allowed_roots

    @property
    def max_bytes(self) -> int:
        """Return the configured maximum file size."""

        return self._max_bytes

    def resolve(self, path: str | Path, *, description: str = "file") -> Path:
        """Resolve *path* ensuring it resides within an allowed root.

        Args:
            path: Candidate path to validate.
            description: Human friendly label for error messages.

        Returns:
            A resolved :class:`pathlib.Path` pointing to the validated file.

        Raises:
            PermissionError: If the resolved path is outside allowed roots or
                is a disallowed symlink.
            FileNotFoundError: If the target does not exist.
            IsADirectoryError: If the resolved object is not a file.
            ValueError: If the target exceeds the configured size limit.
        """

        candidate = Path(path).expanduser()

        if candidate.is_symlink() and not self._follow_symlinks:
            raise PermissionError(
                f"Refusing to read {description} via symlink: {candidate}"
            )

        resolved = candidate.resolve(strict=False)

        if not any(
            self._is_within_root(resolved, root) for root in self._allowed_roots
        ):
            allowed = ", ".join(str(root) for root in self._allowed_roots)
            raise PermissionError(
                f"{description.capitalize()} {candidate} is outside allowed directories: {allowed}"
            )

        if not resolved.exists():
            raise FileNotFoundError(f"{description.capitalize()} not found: {resolved}")

        if not resolved.is_file():
            raise IsADirectoryError(f"Expected {description} to be a file: {resolved}")

        size = resolved.stat().st_size
        if size > self._max_bytes:
            raise ValueError(
                f"{description.capitalize()} {resolved} exceeds allowed size {self._max_bytes} bytes (got {size})"
            )

        return resolved

    @staticmethod
    def _is_within_root(path: Path, root: Path) -> bool:
        try:
            path.resolve(strict=False).relative_to(root)
        except ValueError:
            return False
        else:
            return True


__all__ = ["DataPathGuard"]
