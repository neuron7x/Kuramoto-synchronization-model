from __future__ import annotations

from dataclasses import dataclass

OBSERVATION_KEYS = ("dd", "liq", "reg", "vol")


def _validate_keys(label: str, keys: tuple[str, ...]) -> None:
    if not keys:
        raise ValueError(f"{label} keys must be non-empty.")
    if any(not key for key in keys):
        raise ValueError(f"{label} keys must be non-empty strings.")
    if len(set(keys)) != len(keys):
        raise ValueError(f"{label} keys must be unique.")
    unexpected = set(keys) - set(OBSERVATION_KEYS)
    if unexpected:
        allowed = ", ".join(OBSERVATION_KEYS)
        raise ValueError(
            f"{label} keys contain unexpected values {sorted(unexpected)}. "
            f"Allowed keys: {allowed}."
        )


@dataclass(frozen=True)
class SensoryConfig:
    spatial_lambda: float = 0.25
    temporal_lambda: float = 0.35
    contrast_gain: float = 0.6
    keys: tuple[str, ...] = ("dd", "liq", "reg", "vol")

    def __post_init__(self) -> None:
        normalized = tuple(self.keys)
        _validate_keys("SensoryConfig", normalized)
        object.__setattr__(self, "keys", normalized)


@dataclass(frozen=True)
class PredictiveConfig:
    decay: float = 0.8
    error_gain: float = 0.9
    keys: tuple[str, ...] = ("dd", "liq", "reg", "vol")

    def __post_init__(self) -> None:
        normalized = tuple(self.keys)
        _validate_keys("PredictiveConfig", normalized)
        object.__setattr__(self, "keys", normalized)
