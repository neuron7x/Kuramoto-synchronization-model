"""Fractal barrier utilities coordinating FHMC multi-agent execution."""

from __future__ import annotations

import threading
from typing import Dict, Iterable


class FractalBarrier:
    def __init__(self, levels: Iterable[int] = (1, 2, 4, 8)) -> None:
        unique_levels = sorted({level for level in levels if level > 0})
        self.levels = unique_levels
        self._locks: Dict[int, threading.Barrier] = {
            level: threading.Barrier(level) for level in unique_levels if level > 1
        }

    def wait(self, world_rank: int, world_size: int) -> None:
        level = self._pick_level(world_rank, world_size)
        barrier = self._locks.get(level)
        if barrier is None:
            return
        barrier.wait(timeout=10.0)

    def _pick_level(self, rank: int, size: int) -> int:
        for level in self.levels:
            if size % level == 0 and rank % (size // level) == 0:
                return level
        return 1
