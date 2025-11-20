"""GABAergic inhibition gate moderating impulsive Go drives."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Mapping, Optional

import yaml


@dataclass(frozen=True)
class GABAConfig:
    impulse_decay: float
    impulse_threshold: float
    inhibition_gain: float
    stress_gain: float
    max_inhibition: float
    stdp_lr: float
    stdp_min: float
    stdp_max: float
    rpe_beta: float
    plasticity: bool

    def to_dict(self) -> Dict[str, float | bool]:
        return {
            "impulse_decay": self.impulse_decay,
            "impulse_threshold": self.impulse_threshold,
            "inhibition_gain": self.inhibition_gain,
            "stress_gain": self.stress_gain,
            "max_inhibition": self.max_inhibition,
            "stdp_lr": self.stdp_lr,
            "stdp_min": self.stdp_min,
            "stdp_max": self.stdp_max,
            "rpe_beta": self.rpe_beta,
            "plasticity": self.plasticity,
        }


def _ensure_float(
    name: str,
    value: object,
    *,
    min_value: Optional[float] = None,
    max_value: Optional[float] = None,
) -> float:
    if not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number")
    result = float(value)
    if min_value is not None and result < min_value:
        raise ValueError(f"{name} must be >= {min_value}")
    if max_value is not None and result > max_value:
        raise ValueError(f"{name} must be <= {max_value}")
    return result


def _ensure_bool(name: str, value: object) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be a boolean")
    return value


class GABAInhibitionGate:
    """Compute inhibition coefficients dampening Go drives under impulsivity."""

    def __init__(
        self,
        config_path: str = "configs/gaba.yaml",
        logger: Optional[Callable[[str, float], None]] = None,
    ) -> None:
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(path)
        with path.open("r", encoding="utf-8") as handle:
            raw_cfg = yaml.safe_load(handle)
        self._config = self._validate_config(raw_cfg or {})
        self.config_path = str(path)
        self._logger = logger or (lambda name, value: None)

        self._impulse_trace = 0.0
        self._rpe_trace = 0.0
        self.inhibition = 0.0
        self._weight = 1.0
        self._stdp_dw = 0.0

    def _log(self, name: str, value: float) -> None:
        try:
            self._logger(name, float(value))
        except Exception:  # pragma: no cover - defensive
            pass

    def _validate_config(self, raw: Mapping[str, object]) -> GABAConfig:
        required = {
            "impulse_decay",
            "impulse_threshold",
            "inhibition_gain",
            "stress_gain",
            "max_inhibition",
            "stdp_lr",
            "stdp_min",
            "stdp_max",
            "rpe_beta",
            "plasticity",
        }
        missing = required - set(raw.keys())
        if missing:
            raise ValueError(f"Missing GABA config keys: {sorted(missing)}")
        impulse_decay = _ensure_float(
            "impulse_decay", raw["impulse_decay"], min_value=0.0, max_value=1.0
        )
        impulse_threshold = _ensure_float(
            "impulse_threshold", raw["impulse_threshold"], min_value=0.0
        )
        inhibition_gain = _ensure_float(
            "inhibition_gain", raw["inhibition_gain"], min_value=0.0
        )
        stress_gain = _ensure_float("stress_gain", raw["stress_gain"], min_value=0.0)
        max_inhibition = _ensure_float(
            "max_inhibition", raw["max_inhibition"], min_value=0.0, max_value=0.99
        )
        stdp_lr = _ensure_float("stdp_lr", raw["stdp_lr"], min_value=0.0)
        stdp_min = _ensure_float(
            "stdp_min", raw["stdp_min"], min_value=0.1, max_value=1.0
        )
        stdp_max = _ensure_float(
            "stdp_max", raw["stdp_max"], min_value=stdp_min, max_value=2.0
        )
        rpe_beta = _ensure_float(
            "rpe_beta", raw["rpe_beta"], min_value=0.0, max_value=1.0
        )
        plasticity = _ensure_bool("plasticity", raw["plasticity"])
        return GABAConfig(
            impulse_decay=impulse_decay,
            impulse_threshold=impulse_threshold,
            inhibition_gain=inhibition_gain,
            stress_gain=stress_gain,
            max_inhibition=max_inhibition,
            stdp_lr=stdp_lr,
            stdp_min=stdp_min,
            stdp_max=stdp_max,
            rpe_beta=rpe_beta,
            plasticity=plasticity,
        )

    @property
    def config(self) -> GABAConfig:
        return self._config

    def reset(self) -> None:
        self._impulse_trace = 0.0
        self._rpe_trace = 0.0
        self.inhibition = 0.0
        self._weight = 1.0
        self._stdp_dw = 0.0

    def update(
        self,
        sequence_intensity: float,
        *,
        dt: float = 1.0,
        rpe: float = 0.0,
        stress: float = 0.0,
    ) -> Mapping[str, float]:
        if dt <= 0:
            raise ValueError("dt must be positive")
        seq = float(max(0.0, sequence_intensity))
        stress = float(max(0.0, stress))
        rpe = float(rpe)

        cfg = self._config
        alpha = 1.0 - (1.0 - cfg.impulse_decay) ** dt
        self._impulse_trace += alpha * (seq - self._impulse_trace)

        impulse_drive = max(0.0, self._impulse_trace - cfg.impulse_threshold)
        inhibition = impulse_drive * cfg.inhibition_gain * self._weight
        inhibition *= 1.0 + cfg.stress_gain * stress
        self.inhibition = min(cfg.max_inhibition, max(0.0, inhibition))

        self._stdp_dw = 0.0
        if cfg.plasticity and cfg.stdp_lr > 0.0 and impulse_drive > 0.0:
            beta = cfg.rpe_beta
            self._rpe_trace += beta * (rpe - self._rpe_trace)
            dw = cfg.stdp_lr * (rpe - self._rpe_trace) * impulse_drive
            new_weight = min(cfg.stdp_max, max(cfg.stdp_min, self._weight + dw))
            self._stdp_dw = new_weight - self._weight
            self._weight = new_weight

        self._log("tacl.gaba.inhib", self.inhibition)
        self._log("tacl.gaba.stdp_dw", self._stdp_dw)

        return {
            "inhibition": self.inhibition,
            "weight": self._weight,
            "impulse_trace": self._impulse_trace,
            "stdp_dw": self._stdp_dw,
        }

    def to_dict(self) -> Mapping[str, float]:
        return {
            "inhibition": self.inhibition,
            "weight": self._weight,
            "impulse_trace": self._impulse_trace,
            "stdp_dw": self._stdp_dw,
        }
