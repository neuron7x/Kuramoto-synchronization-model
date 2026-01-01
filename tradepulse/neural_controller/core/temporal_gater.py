from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Callable, Dict, Mapping, TypeVar


T = TypeVar("T")


@dataclass
class TemporalGater:
    """Gate updates according to a fractional cadence.

    The gater advances on every call to :meth:`step`. When the configured
    frequency accumulates to 1.0 or more, a new update is allowed. Between
    updates, the last value is held constant. When cadence is ``ema``, new
    values are blended with the stored value using ``ema_alpha``.
    """

    frequency: float = 1.0
    cadence: str = "step"
    ema_alpha: float = 0.5
    _phase: float = field(default=0.0, init=False)
    _value: T | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        if self.frequency <= 0:
            raise ValueError("frequency must be positive")
        cadence = self.cadence.lower()
        if cadence not in {"step", "ema"}:
            raise ValueError("cadence must be 'step' or 'ema'")
        if not 0.0 < self.ema_alpha <= 1.0:
            raise ValueError("ema_alpha must be in (0, 1]")
        self.cadence = cadence

    def _advance(self) -> bool:
        self._phase += self.frequency
        if self._phase >= 1.0:
            self._phase -= 1.0
            return True
        return False

    def _clone(self, value: T) -> T:
        return deepcopy(value)

    def _blend_mapping(self, prev: Mapping[str, float], new: Mapping[str, float]) -> Dict[str, float]:
        return {
            key: prev.get(key, 0.0) + self.ema_alpha * (float(value) - prev.get(key, 0.0))
            for key, value in new.items()
        }

    def _blend(self, prev: T, new: T) -> T:
        if isinstance(prev, Mapping) and isinstance(new, Mapping):
            blended = self._blend_mapping(prev, new)
            return self._clone(blended)  # type: ignore[return-value]
        if isinstance(prev, (int, float)) and isinstance(new, (int, float)):
            return self._clone(prev + self.ema_alpha * (new - prev))
        raise TypeError("ema cadence only supports numeric or mapping values")

    def step(self, compute: Callable[[], T]) -> tuple[T, bool]:
        """Return the gated value and whether an update occurred."""

        if self._value is None:
            value = compute()
            self._value = self._clone(value)
            return self._clone(self._value), True
        if not self._advance():
            return self._clone(self._value), False
        value = compute()
        if self.cadence == "ema":
            self._value = self._blend(self._value, value)
        else:
            self._value = self._clone(value)
        return self._clone(self._value), True

    def value(self) -> T | None:
        if self._value is None:
            return None
        return self._clone(self._value)
