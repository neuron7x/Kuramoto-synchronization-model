from __future__ import annotations

import math
from typing import Optional, Mapping, Callable

import numpy as np
import yaml


class SerotoninController:
    def __init__(
        self,
        config_path: str = "configs/serotonin.yaml",
        logger: Optional[Callable[[str, float], None]] = None,
    ):
        self.config_path = config_path
        with open(config_path, "r") as f:
            self.config = yaml.safe_load(f)
        self.tonic_level: float = 0.0
        self.sensitivity: float = 1.0
        self.desens_counter: int = 0
        self.serotonin_level: float = 0.0
        self._logger = logger or self._default_logger

    def _default_logger(self, name: str, value: float) -> None:
        try:
            from neuropro.logging import Logger  # type: ignore
            _lg = Logger()
            if getattr(_lg, "mlflow", None) and _lg.run:
                _lg.mlflow.log_metric(name, float(value))
        except Exception:
            return

    def _log(self, name: str, value: float) -> None:
        try:
            self._logger(name, float(value))
        except Exception:
            pass

    def estimate_aversive_state(
        self,
        market_vol: float,
        free_energy: float,
        cum_losses: float,
        rho_loss: float,
        override_weights: Optional[Mapping[str, float]] = None,
    ) -> float:
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
        return float(release)

    def compute_serotonin_signal(self, aversive_state: float) -> float:
        cfg = self.config
        decay = cfg["decay_rate"]
        self.tonic_level = (1.0 - decay) * self.tonic_level + decay * float(
            aversive_state
        )
        k = cfg["k"]
        theta = cfg["theta"]
        x = k * (self.tonic_level - theta)
        x = max(min(x, 60.0), -60.0)
        sig = 1.0 / (1.0 + math.exp(-x))
        if self.tonic_level > cfg["cooldown_threshold"]:
            self.desens_counter += 1
            if self.desens_counter > cfg["desens_threshold_ticks"]:
                self.sensitivity = max(0.1, self.sensitivity - cfg["desens_rate"])
        else:
            self.desens_counter = max(0, self.desens_counter - 1)
            recovery_boost = 1.0 + self.desens_counter / max(
                cfg["desens_threshold_ticks"], 1
            )
            self.sensitivity = min(
                1.0,
                self.sensitivity + cfg["desens_rate"] * recovery_boost,
            )
        self.serotonin_level = float(sig * self.sensitivity)
        return self.serotonin_level

    def modulate_action_prob(
        self,
        original_prob: float,
        serotonin_signal: Optional[float] = None,
        za_bias: Optional[float] = None,
    ) -> float:
        cfg = self.config
        if serotonin_signal is None:
            serotonin_signal = self.serotonin_level
        if za_bias is None:
            za_bias = cfg["za_bias"]
        inhibited = original_prob * (1.0 - serotonin_signal * cfg["delta"])
        biased = inhibited * (1.0 + za_bias)
        return float(np.clip(biased, 0.0, 1.0))

    def check_cooldown(self, serotonin_signal: Optional[float] = None) -> bool:
        if serotonin_signal is None:
            serotonin_signal = self.serotonin_level
        return serotonin_signal > self.config["cooldown_threshold"]

    def apply_internal_shift(
        self,
        exploitation_gradient: float,
        serotonin_signal: Optional[float] = None,
        beta_temper: Optional[float] = None,
    ) -> float:
        if serotonin_signal is None:
            serotonin_signal = self.serotonin_level
        if beta_temper is None:
            beta_temper = self.config["beta_temper"]
        return float(exploitation_gradient * (1.0 - beta_temper * serotonin_signal))

    def update_metrics(self) -> None:
        self._log("serotonin_level", self.serotonin_level)
        self._log("serotonin_tonic_level", self.tonic_level)
        self._log("serotonin_sensitivity", self.sensitivity)

    def meta_adapt(self, performance_metrics: Mapping[str, float]) -> None:
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
        target = path or self.config_path
        with open(target, "w") as f:
            yaml.safe_dump(self.config, f)

    def to_dict(self) -> dict:
        return {
            "tonic_level": float(self.tonic_level),
            "sensitivity": float(self.sensitivity),
            "desens_counter": int(self.desens_counter),
            "serotonin_level": float(self.serotonin_level),
            "alpha": float(self.config["alpha"]),
            "beta": float(self.config["beta"]),
            "gamma": float(self.config["gamma"]),
        }
