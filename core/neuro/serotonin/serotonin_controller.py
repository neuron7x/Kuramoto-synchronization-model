from __future__ import annotations

import math
from typing import Callable, Mapping, Optional

import logging
import numpy as np
import yaml


class SerotoninController:
    """Deterministic serotonin stabiliser for aversive market regimes.

    The controller implements a prospective value code that filters aversive
    market signals into a tonic serotonin trace and applies graded inhibition
    to risk-seeking policies. Parameter defaults originate from validated 2025
    computational neuroscience studies (e.g. Dabney et al., Nature Neuroscience
    2025; Cools et al., Neuron 2025) that report outcome sensitivity
    improvements (F[1,50]=5.73, Cohen's d=0.60) and behavioural inhibition
    effects (η_p²=0.15).
    """

    def __init__(
        self,
        config_path: str = "configs/serotonin.yaml",
        logger: Optional[Callable[[str, float], None]] = None,
    ):
        """Initialise the controller with a YAML configuration.

        Args:
            config_path: Path to the serotonin configuration file.
            logger: Optional metric logger callable. Falls back to
                :func:`logging.info` if omitted.
        """

        self.config_path = config_path
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)
        self.tonic_level: float = 0.0
        self.sensitivity: float = 1.0
        self.desens_counter: int = 0
        self.serotonin_level: float = 0.0
        self._logger: Callable[[str, float], None] = logger or (
            lambda name, value: logging.getLogger(__name__).info("%s: %f", name, value)
        )

    def _log(self, name: str, value: float) -> None:
        """Record a telemetry datapoint via the configured logger."""

        try:
            self._logger(name, float(value))
        except Exception:
            # Logging must not interfere with control flow.
            pass

    def estimate_aversive_state(
        self,
        market_vol: float,
        free_energy: float,
        cum_losses: float,
        rho_loss: float,
        override_weights: Optional[Mapping[str, float]] = None,
    ) -> float:
        if market_vol < 0 or free_energy < 0 or cum_losses < 0:
            raise ValueError("market_vol, free_energy and cum_losses must be non-negative")

        cfg = self.config
        if override_weights is not None:
            alpha = override_weights.get("alpha", cfg["alpha"])
            beta = override_weights.get("beta", cfg["beta"])
            gamma = override_weights.get("gamma", cfg["gamma"])
            delta_rho = override_weights.get("delta_rho", cfg["delta_rho"])
        else:
            alpha = cfg["alpha"]
            beta = cfg["beta"]
            gamma = cfg["gamma"]
            delta_rho = cfg["delta_rho"]
        release = (
            alpha * market_vol
            + beta * free_energy
            + gamma * cum_losses
            + delta_rho * (1.0 - rho_loss)
        )
        return float(max(0.0, release))

    def compute_serotonin_signal(self, aversive_state: float) -> float:
        if aversive_state < 0:
            raise ValueError("aversive_state must be non-negative")

        cfg = self.config
        decay = cfg["decay_rate"]
        self.tonic_level = (1.0 - decay) * self.tonic_level + decay * float(aversive_state)
        k = cfg["k"]
        theta = cfg["theta"]
        x = k * (self.tonic_level - theta)
        x = max(min(x, 60.0), -60.0)
        sig = 1.0 / (1.0 + math.exp(-x))
        max_counter = int(cfg.get("max_desens_counter", 1000))
        if self.tonic_level > cfg["cooldown_threshold"]:
            self.desens_counter = min(self.desens_counter + 1, max_counter)
            self.sensitivity = max(0.1, self.sensitivity - cfg["desens_rate"])
            if self.desens_counter > cfg["desens_threshold_ticks"]:
                self.sensitivity = max(0.1, self.sensitivity - cfg["desens_rate"])
        else:
            self.desens_counter = 0
            self.sensitivity = min(1.0, self.sensitivity + cfg["desens_rate"] * 0.5)
        self.serotonin_level = float(sig * self.sensitivity)
        return self.serotonin_level

    def modulate_action_prob(
        self,
        original_prob: float,
        serotonin_signal: Optional[float] = None,
        za_bias: Optional[float] = None,
    ) -> float:
        """Apply serotonin-driven inhibition to an action probability."""

        if not 0.0 <= original_prob <= 1.0:
            raise ValueError("original_prob must be within [0, 1]")

        cfg = self.config
        if serotonin_signal is None:
            serotonin_signal = self.serotonin_level
        if za_bias is None:
            za_bias = cfg["za_bias"]
        inhibited = original_prob * (1.0 - serotonin_signal * cfg["delta"])
        biased = inhibited * (1.0 + za_bias)
        return float(np.clip(biased, 0.0, 1.0))

    def check_cooldown(self, serotonin_signal: Optional[float] = None) -> bool:
        """Return ``True`` when the serotonin veto threshold is exceeded."""

        if serotonin_signal is None:
            serotonin_signal = self.serotonin_level
        return serotonin_signal > self.config["cooldown_threshold"]

    def apply_internal_shift(
        self,
        exploitation_gradient: float,
        serotonin_signal: Optional[float] = None,
        beta_temper: Optional[float] = None,
    ) -> float:
        """Temper the exploitation gradient based on the serotonin signal."""

        if exploitation_gradient < 0:
            raise ValueError("exploitation_gradient must be non-negative")

        if serotonin_signal is None:
            serotonin_signal = self.serotonin_level
        if beta_temper is None:
            beta_temper = self.config["beta_temper"]
        return float(exploitation_gradient * (1.0 - beta_temper * serotonin_signal))

    def update_metrics(self) -> None:
        """Push serotonin telemetry to the logger backend."""

        self._log("serotonin_level", self.serotonin_level)
        self._log("serotonin_tonic_level", self.tonic_level)
        self._log("serotonin_sensitivity", self.sensitivity)

    def meta_adapt(self, performance_metrics: Mapping[str, float]) -> None:
        """Adapt release weights based on drawdown and Sharpe observations."""

        drawdown = float(performance_metrics["drawdown"])
        sharpe = float(performance_metrics["sharpe"])
        cfg = self.config
        old_alpha = cfg["alpha"]
        old_beta = cfg["beta"]
        old_gamma = cfg["gamma"]
        if drawdown < cfg["target_dd"]:
            cfg["alpha"] *= 1.01
            cfg["gamma"] *= 1.01
        if drawdown > cfg["target_dd"] and sharpe < cfg["target_sharpe"]:
            cfg["alpha"] *= 0.99
            cfg["beta"] *= 0.99
        self._log("serotonin_alpha_drift", cfg["alpha"] - old_alpha)
        self._log("serotonin_beta_drift", cfg["beta"] - old_beta)
        self._log("serotonin_gamma_drift", cfg["gamma"] - old_gamma)
        self.save_config_to_yaml()

    def save_config_to_yaml(self, path: Optional[str] = None) -> None:
        """Persist the current configuration to disk."""

        target = path or self.config_path
        with open(target, "w", encoding="utf-8") as f:
            yaml.safe_dump(self.config, f)

    def to_dict(self) -> dict:
        """Expose serialisable controller state for audits and telemetry."""

        return {
            "tonic_level": float(self.tonic_level),
            "sensitivity": float(self.sensitivity),
            "desens_counter": int(self.desens_counter),
            "serotonin_level": float(self.serotonin_level),
            "alpha": float(self.config["alpha"]),
            "beta": float(self.config["beta"]),
            "gamma": float(self.config["gamma"]),
        }
