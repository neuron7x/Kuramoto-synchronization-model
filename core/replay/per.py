"""Prioritized experience replay with breach boosting."""

from __future__ import annotations

from collections import deque
from typing import Deque, Iterable, List, Optional, Tuple

import numpy as np

Transition = Tuple[np.ndarray, int, float, np.ndarray, bool]


class PERBuffer:
    """Proportional PER buffer supporting importance sampling weights."""

    def __init__(self, capacity: int, alpha: float, beta: float, eps: float) -> None:
        self.capacity = int(capacity)
        self.alpha = float(alpha)
        self.beta = float(beta)
        self.eps = float(eps)
        self.storage: List[Transition] = []
        self.priorities: List[float] = []
        self.pos = 0
        self._breach_queue: Deque[int] = deque(maxlen=capacity)
        self._breach_boost = 1.0

    def __len__(self) -> int:
        return len(self.storage)

    def configure_breach(self, boost: float) -> None:
        self._breach_boost = max(1.0, float(boost))

    def mark_recent(self, window: int) -> None:
        if window <= 0:
            return
        total = len(self.storage)
        start = max(total - window, 0)
        self._breach_queue.extend(range(start, total))

    def add(self, transition: Transition, priority: float | None = None) -> None:
        priority_value = float(abs(priority) + self.eps) if priority is not None else None
        if priority_value is None:
            priority_value = max(self.priorities, default=1.0)
        if len(self.storage) < self.capacity:
            self.storage.append(transition)
            self.priorities.append(priority_value)
        else:
            self.storage[self.pos] = transition
            self.priorities[self.pos] = priority_value
            self.pos = (self.pos + 1) % self.capacity

    def sample(self, batch_size: int) -> tuple[list[int], list[Transition], np.ndarray]:
        if len(self.storage) == 0:
            raise ValueError("Cannot sample from empty buffer")
        priorities = np.asarray(self.priorities, dtype=np.float64)
        scaled = priorities ** self.alpha
        probs = scaled / scaled.sum()
        idxs = np.random.choice(len(self.storage), batch_size, p=probs)
        samples = [self.storage[i] for i in idxs]
        weights = (len(self.storage) * probs[idxs]) ** (-self.beta)
        weights = (weights / weights.max()).astype(np.float32)
        return idxs.tolist(), samples, weights

    def update_priorities(self, idxs: list[int], new_p: np.ndarray) -> None:
        for idx, val in zip(idxs, new_p):
            boost = self._breach_boost if idx in self._breach_queue else 1.0
            self.priorities[idx] = float(abs(val) * boost + self.eps)
        self._breach_queue.clear()
