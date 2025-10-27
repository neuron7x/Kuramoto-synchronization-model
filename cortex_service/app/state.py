"""Mutable runtime state for the cognition service."""

from __future__ import annotations

from threading import Lock

from .config import RegimeSettings


class RegimeController:
    """Thread-safe controller that tracks the global valence."""

    def __init__(self, settings: RegimeSettings):
        self._settings = settings
        self._valence = self._clamp(settings.initial_valence)
        self._lock = Lock()

    def current(self) -> float:
        """Return the current valence."""

        with self._lock:
            return self._valence

    def apply_feedback(self, feedback: float) -> float:
        """Blend the feedback into the stored valence and return the update."""

        with self._lock:
            decay = self._settings.decay
            updated = (1 - decay) * self._valence + decay * feedback
            self._valence = self._clamp(updated)
            return self._valence

    def _clamp(self, value: float) -> float:
        return max(self._settings.min_valence, min(self._settings.max_valence, value))


__all__ = ["RegimeController"]
