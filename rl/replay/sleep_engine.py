"""Sleep-inspired replay buffer with novelty-aware prioritisation."""

from __future__ import annotations

from collections import deque, namedtuple
from typing import Any, Deque, List

import numpy as np

Transition = namedtuple(
    "Transition", "state action reward next_state priority cp_score"
)


class SleepReplayEngine:
    """Prioritised replay buffer that supports dream-like regeneration."""

    def __init__(
        self,
        *,
        capacity: int = 100_000,
        psi: float = 0.5,
        phi: float = 0.3,
        dgr_ratio: float = 0.25,
    ) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self.buffer: Deque[Transition] = deque(maxlen=int(capacity))
        self.psi = float(psi)
        self.phi = float(phi)
        self.dgr_ratio = float(dgr_ratio)

    def __len__(self) -> int:  # pragma: no cover - trivial
        return len(self.buffer)

    def observe_transition(
        self,
        state: np.ndarray,
        action: np.ndarray,
        reward: float,
        next_state: np.ndarray,
        td_error: float,
        *,
        cp_score: float = 0.0,
        imminence_jump: float = 0.0,
    ) -> float:
        priority = abs(td_error) + self.psi * cp_score + self.phi * imminence_jump
        transition = Transition(
            np.array(state, copy=True),
            np.array(action, copy=True),
            float(reward),
            np.array(next_state, copy=True),
            float(priority),
            float(cp_score),
        )
        self.buffer.append(transition)
        return float(priority)

    def sample(self, batch_size: int = 64) -> List[Transition]:
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")
        if not self.buffer:
            return []
        priorities = np.array(
            [transition.priority for transition in self.buffer], dtype=float
        )
        total_priority = float(np.sum(priorities))
        if not np.isfinite(total_priority) or total_priority <= 0.0:
            probabilities = np.full(len(self.buffer), 1.0 / len(self.buffer))
        else:
            probabilities = priorities / total_priority
        replace = len(self.buffer) < batch_size
        indices = np.random.choice(
            len(self.buffer), size=batch_size, replace=replace, p=probabilities
        )
        return [self.buffer[index] for index in indices]

    def dgr_batch(self, generator: Any, m: int) -> List[Any]:
        if generator is None or m <= 0:
            return []
        if not hasattr(generator, "sample"):
            raise TypeError("generator must expose a sample method")
        return list(generator.sample(m))
