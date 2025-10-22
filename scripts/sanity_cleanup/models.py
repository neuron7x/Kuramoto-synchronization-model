"""Typed data structures shared across sanity cleanup modules."""

from __future__ import annotations

# SPDX-License-Identifier: MIT
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Mapping, Sequence


class TaskStatus(str, Enum):
    """Possible outcomes for a cleanup task."""

    SUCCESS = "success"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass(frozen=True)
class TaskReport:
    """Detailed metadata for the execution of a task."""

    name: str
    status: TaskStatus
    summary: str
    details: Sequence[str] = field(default_factory=tuple)
    artifacts: Mapping[str, Path] | None = None


@dataclass(frozen=True)
class CleanupOptions:
    """Configuration for running the cleanup pipeline."""

    dry_run: bool = False
    archive_legacy: bool = False
    include_patterns: Sequence[str] | None = None
    exclude_patterns: Sequence[str] | None = None


@dataclass(frozen=True)
class TaskContext:
    """Runtime context shared by all tasks."""

    root: Path
    options: CleanupOptions
