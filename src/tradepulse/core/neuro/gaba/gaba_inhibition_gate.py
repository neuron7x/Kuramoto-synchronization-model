"""GABAergic inhibition gate moderating impulsive Go drives.

This module implements GABA-inspired inhibition mechanisms that dampen
impulsive trading decisions under high volatility or stress conditions.

Public API
----------
GABAConfig : Configuration dataclass for the inhibition gate
GABAInhibitionGate : Main inhibition gate class with update() interface

The gate computes inhibition coefficients that reduce Go drives when
impulsivity (measured by sequence intensity) exceeds threshold levels.
STDP-like plasticity allows the gate to adapt based on prediction errors.

Performance Notes
-----------------
- Algorithmic complexity: O(1) per update call
- All magic numbers extracted to GABAConfig for production-grade configurability
- Uses numpy-based sanitization for robust handling of non-finite values
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Mapping, Optional

import numpy as np
import yaml

from .._validation import ensure_bool, ensure_float


def _sanitize_scalar(value: float, default: float = 0.0) -> float:
    """Sanitize a scalar value, replacing NaN/Inf with default.

    Args:
        value: Input scalar value to sanitize.
        default: Default value to use if input is non-finite.

    Returns:
        float: Sanitized value (either original or default).
    """
    if not np.isfinite(value):
        return default
    return float(value)


@dataclass(frozen=True)
class GABAConfig:
    """Configuration container for :class:`GABAInhibitionGate`.

    Attributes
    ----------
    impulse_decay : float
        EMA decay rate for impulse trace [0, 1]
    impulse_threshold : float
        Threshold above which inhibition is triggered
    inhibition_gain : float
        Multiplier for converting impulse drive to inhibition
    stress_gain : float
        Additional inhibition gain under stress conditions
    max_inhibition : float
        Maximum inhibition level [0, 0.99]
    stdp_lr : float
        Learning rate for STDP-like weight updates
    stdp_min : float
        Minimum STDP weight [0.1, 1.0]
    stdp_max : float
        Maximum STDP weight [stdp_min, 2.0]
    rpe_beta : float
        EMA decay rate for RPE trace [0, 1]
    plasticity : bool
        Enable/disable STDP-like weight plasticity
    """

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
        """Convert configuration to dictionary representation."""
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
        except Exception as exc:  # pragma: no cover - defensive
            logging.getLogger(__name__).debug(
                "GABAInhibitionGate logger failed for %s: %s", name, exc
            )

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
        impulse_decay = ensure_float(
            "impulse_decay", raw["impulse_decay"], min_value=0.0, max_value=1.0
        )
        impulse_threshold = ensure_float(
            "impulse_threshold", raw["impulse_threshold"], min_value=0.0
        )
        inhibition_gain = ensure_float(
            "inhibition_gain", raw["inhibition_gain"], min_value=0.0
        )
        stress_gain = ensure_float("stress_gain", raw["stress_gain"], min_value=0.0)
        max_inhibition = ensure_float(
            "max_inhibition", raw["max_inhibition"], min_value=0.0, max_value=0.99
        )
        stdp_lr = ensure_float("stdp_lr", raw["stdp_lr"], min_value=0.0)
        stdp_min = ensure_float(
            "stdp_min", raw["stdp_min"], min_value=0.1, max_value=1.0
        )
        stdp_max = ensure_float(
            "stdp_max", raw["stdp_max"], min_value=stdp_min, max_value=2.0
        )
        rpe_beta = ensure_float(
            "rpe_beta", raw["rpe_beta"], min_value=0.0, max_value=1.0
        )
        plasticity = ensure_bool("plasticity", raw["plasticity"])
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
        """Update the GABA inhibition gate with new inputs.

        Computes inhibition coefficient based on impulse trace and stress.
        Uses STDP-like plasticity to adapt weights based on RPE feedback.

        Args:
            sequence_intensity: Current action sequence intensity (≥ 0).
            dt: Time delta for EMA updates (> 0, default 1.0).
            rpe: Reward prediction error for STDP plasticity.
            stress: Stress level for enhanced inhibition (≥ 0).

        Returns:
            Mapping with keys: inhibition, weight, impulse_trace, stdp_dw.

        Raises:
            ValueError: If dt ≤ 0.

        Note:
            Algorithmic complexity: O(1) per call.
            Uses robust sanitization for non-finite inputs.
        """
        if dt <= 0:
            raise ValueError("dt must be positive")

        # Robust sanitization of inputs using np.nan_to_num equivalent
        seq = _sanitize_scalar(float(sequence_intensity), 0.0)
        seq = max(0.0, seq)
        stress = _sanitize_scalar(float(stress), 0.0)
        stress = max(0.0, stress)
        rpe = _sanitize_scalar(float(rpe), 0.0)

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
