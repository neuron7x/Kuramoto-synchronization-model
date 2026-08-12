# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Lightweight progress reporting utilities."""

from __future__ import annotations

# SPDX-License-Identifier: MIT
import sys
import time
from dataclasses import dataclass, field
from typing import IO


@dataclass(slots=True)
class ProgressBar:
    """A simple textual progress bar that displays ETA for long operations."""

    total: int | None = None
    label: str = ""
    stream: IO[str] = field(default_factory=lambda: sys.stderr)
    width: int = 30
    _start: float = field(init=False, default=0.0)
    _current: int = field(init=False, default=0)
    _last_render: float = field(init=False, default=0.0)

    def __post_init__(self) -> None:
        self._start = time.monotonic()
        self._current = 0
        self._last_render = 0.0

    def __enter__(self) -> "ProgressBar":
        self.render(force=True)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[override]
        self.finish()

    @property
    def current(self) -> int:
        return self._current

    def advance(self, steps: int = 1) -> None:
        self.update(self._current + steps)

    def update(self, value: int) -> None:
        self._current = max(0, value)
        self.render()

    def finish(self) -> None:
        self._current = self.total or self._current
        self.render(force=True)
        self.stream.write("\n")
        self.stream.flush()

    def _format_eta(self) -> str:
        if self.total is None or self._current <= 0:
            return "?"
        elapsed = time.monotonic() - self._start
        rate = self._current / elapsed if elapsed > 0 else 0
        if rate <= 0:
            return "?"
        remaining = max(self.total - self._current, 0)
        eta_seconds = remaining / rate
        return time.strftime("%H:%M:%S", time.gmtime(eta_seconds))

    def render(self, *, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._last_render < 0.1:
            return
        self._last_render = now
        if self.total:
            ratio = min(max(self._current / self.total, 0.0), 1.0)
            filled = int(self.width * ratio)
            bar = "█" * filled + "─" * (self.width - filled)
            percent = f"{ratio * 100:5.1f}%"
            eta = self._format_eta()
            message = f"{self.label} [{bar}] {percent} ETA {eta}"
        else:
            message = f"{self.label} {self._current} completed"
        self.stream.write("\r" + message)
        self.stream.flush()
