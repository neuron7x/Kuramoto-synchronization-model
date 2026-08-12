# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Noradrenaline (NA) and acetylcholine (ACh) neuromodulation utilities.

This module implements NA/ACh neuromodulator controllers that model arousal
and attention dynamics for the trading system. These modulators affect:
- Risk tolerance (via arousal levels)
- Exploration temperature (via attention levels)

Public API
----------
NAACHConfig : Configuration dataclass for the neuromodulator
NAACHNeuromodulator : Main neuromodulator class with update() interface
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Mapping, Optional

import yaml

from .._validation import ensure_float


@dataclass(frozen=True)
class NAACHConfig:
    """Configuration container for :class:`NAACHNeuromodulator`.

    Attributes
    ----------
    arousal_baseline : float
        Baseline arousal level (NA component)
    arousal_gain : float
        Sensitivity of arousal to volatility changes
    arousal_min : float
        Minimum arousal level
    arousal_max : float
        Maximum arousal level
    risk_min : float
        Minimum risk multiplier
    risk_max : float
        Maximum risk multiplier
    attention_baseline : float
        Baseline attention level (ACh component)
    attention_gain : float
        Sensitivity of attention to novelty changes
    attention_min : float
        Minimum attention level
    attention_max : float
        Maximum attention level
    temp_gain : float
        Gain for temperature scaling from arousal [0, 3]
    """

    arousal_baseline: float
    arousal_gain: float
    arousal_min: float
    arousal_max: float
    risk_min: float
    risk_max: float
    attention_baseline: float
    attention_gain: float
    attention_min: float
    attention_max: float
    temp_gain: float

    def to_dict(self) -> Dict[str, float]:
        """Convert configuration to dictionary representation."""
        return {
            "arousal_baseline": self.arousal_baseline,
            "arousal_gain": self.arousal_gain,
            "arousal_min": self.arousal_min,
            "arousal_max": self.arousal_max,
            "risk_min": self.risk_min,
            "risk_max": self.risk_max,
            "attention_baseline": self.attention_baseline,
            "attention_gain": self.attention_gain,
            "attention_min": self.attention_min,
            "attention_max": self.attention_max,
            "temp_gain": self.temp_gain,
        }


class NAACHNeuromodulator:
    """Compute NA/ACh neuromodulator levels and derived scalers."""

    def __init__(
        self,
        config_path: str = "configs/na_ach.yaml",
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
        self.arousal = self._config.arousal_baseline
        self.attention = self._config.attention_baseline

    def _log(self, name: str, value: float) -> None:
        try:
            self._logger(name, float(value))
        except Exception as exc:  # pragma: no cover - defensive
            logging.getLogger(__name__).debug(
                "NAACHNeuromodulator logger failed for %s: %s", name, exc
            )

    def _validate_config(self, raw: Mapping[str, object]) -> NAACHConfig:
        required = {
            "arousal_baseline",
            "arousal_gain",
            "arousal_min",
            "arousal_max",
            "risk_min",
            "risk_max",
            "attention_baseline",
            "attention_gain",
            "attention_min",
            "attention_max",
            "temp_gain",
        }
        missing = required - set(raw.keys())
        if missing:
            raise ValueError(f"Missing NA/ACh config keys: {sorted(missing)}")
        arousal_baseline = ensure_float("arousal_baseline", raw["arousal_baseline"], min_value=0.0)
        arousal_gain = ensure_float("arousal_gain", raw["arousal_gain"], min_value=0.0)
        arousal_min = ensure_float("arousal_min", raw["arousal_min"], min_value=0.0)
        arousal_max = ensure_float("arousal_max", raw["arousal_max"], min_value=arousal_min)
        risk_min = ensure_float("risk_min", raw["risk_min"], min_value=0.0)
        risk_max = ensure_float("risk_max", raw["risk_max"], min_value=risk_min)
        attention_baseline = ensure_float(
            "attention_baseline", raw["attention_baseline"], min_value=0.0
        )
        attention_gain = ensure_float("attention_gain", raw["attention_gain"], min_value=0.0)
        attention_min = ensure_float("attention_min", raw["attention_min"], min_value=0.0)
        attention_max = ensure_float("attention_max", raw["attention_max"], min_value=attention_min)
        temp_gain = ensure_float("temp_gain", raw["temp_gain"], min_value=0.0, max_value=3.0)
        return NAACHConfig(
            arousal_baseline=arousal_baseline,
            arousal_gain=arousal_gain,
            arousal_min=arousal_min,
            arousal_max=arousal_max,
            risk_min=risk_min,
            risk_max=risk_max,
            attention_baseline=attention_baseline,
            attention_gain=attention_gain,
            attention_min=attention_min,
            attention_max=attention_max,
            temp_gain=temp_gain,
        )

    @property
    def config(self) -> NAACHConfig:
        return self._config

    def update(self, volatility: float, novelty: float) -> Mapping[str, float]:
        vol = float(max(0.0, volatility))
        nov = float(max(0.0, novelty))
        cfg = self._config

        self.arousal = min(
            cfg.arousal_max,
            max(
                cfg.arousal_min,
                cfg.arousal_baseline + cfg.arousal_gain * (vol - cfg.arousal_baseline),
            ),
        )
        self.attention = min(
            cfg.attention_max,
            max(
                cfg.attention_min,
                cfg.attention_baseline + cfg.attention_gain * (nov - cfg.attention_baseline),
            ),
        )

        risk_multiplier = max(
            cfg.risk_min, min(cfg.risk_max, 1.0 + (self.arousal - cfg.arousal_baseline))
        )
        temperature_scale = max(0.2, min(3.0, 1.0 + cfg.temp_gain * (1.0 - self.arousal)))

        self._log("tacl.na.arousal", self.arousal)
        self._log("tacl.ach.attn", self.attention)

        return {
            "arousal": self.arousal,
            "attention": self.attention,
            "risk_multiplier": risk_multiplier,
            "temperature_scale": temperature_scale,
        }

    def to_dict(self) -> Mapping[str, float]:
        return {
            "arousal": self.arousal,
            "attention": self.attention,
        }
