from __future__ import annotations

import math
from typing import Callable, Mapping, Optional

import logging
import numpy as np
import yaml


class SerotoninController:
    """SerotoninController v2.3.1 tonic–phasic stabiliser with TACL guardrails."""

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
        self._validate_and_derive()
        self.tonic_level: float = 0.0
        self.sensitivity: float = 1.0
        self.desens_counter: int = 0
        self.serotonin_level: float = 0.0
        self.phasic_level: float = 0.0
        self.gate_level: float = 0.0
        self._logger: Callable[[str, float], None] = logger or (
            lambda name, value: logging.getLogger(__name__).info("%s: %f", name, value)
        )
        self._tacl_guard: Optional[Callable[[str, Mapping[str, float]], bool]] = None

    def _log(self, name: str, value: float) -> None:
        """Record a telemetry datapoint via the configured logger."""

        try:
            self._logger(name, float(value))
        except Exception:
            # Logging must not interfere with control flow.
            pass

    def _validate_and_derive(self) -> None:
        """Validate configuration keys and derive dependent quantities."""

        cfg = self.config
        tau_ms = float(cfg.get("tau_5ht_ms", 0.0) or 0.0)
        step_ms = float(cfg.get("step_ms", 0.0) or 0.0)
        if tau_ms > 0.0 and step_ms > 0.0:
            cfg["decay_rate"] = 1.0 - math.exp(-step_ms / tau_ms)
        self._tick_hours: float = float(cfg.get("tick_hours", 1.0) or 1.0)
        required = [
            "alpha",
            "beta",
            "gamma",
            "delta_rho",
            "k",
            "theta",
            "delta",
            "za_bias",
            "decay_rate",
            "cooldown_threshold",
            "desens_threshold_ticks",
            "desens_rate",
            "target_dd",
            "target_sharpe",
            "beta_temper",
            "phase_threshold",
            "burst_factor",
            "mod_t_max",
            "mod_t_half",
            "mod_k",
            "max_desens_counter",
        ]
        missing = [key for key in required if key not in cfg]
        if missing:
            raise KeyError(f"Serotonin configuration is missing keys: {missing}")

    def set_tacl_guard(self, guard_fn: Callable[[str, Mapping[str, float]], bool]) -> None:
        """Inject a TACL guard to prevent free-energy regressions."""

        self._tacl_guard = guard_fn

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
        kappa = float(cfg.get("phase_kappa", 0.08) or 0.08)
        gate = 1.0 / (1.0 + math.exp(-(aversive_state - cfg["phase_threshold"]) / kappa))
        self.gate_level = float(gate)
        self.phasic_level = float(
            cfg["burst_factor"] * gate * (aversive_state / (1.0 + aversive_state))
        )
        decay = cfg["decay_rate"]
        self.tonic_level = (1.0 - decay) * self.tonic_level + decay * (
            float(aversive_state) + self.phasic_level
        )
        k = cfg["k"]
        theta = cfg["theta"]
        x = k * (self.tonic_level - theta)
        x = max(min(x, 60.0), -60.0)
        sig = 1.0 / (1.0 + math.exp(-x))
        max_counter = int(cfg["max_desens_counter"])
        if self.tonic_level > cfg["cooldown_threshold"]:
            self.desens_counter = min(self.desens_counter + 1, max_counter)
            if self.desens_counter > cfg["desens_threshold_ticks"]:
                self.sensitivity = max(0.1, self.sensitivity * math.exp(-sig / 12.0))
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
        return (
            serotonin_signal > self.config["cooldown_threshold"]
            or self.phasic_level > 1.0
            or self.gate_level > 0.9
        )

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
        self._log("serotonin_phasic_level", self.phasic_level)
        self._log("serotonin_gate_level", self.gate_level)

    def meta_adapt(self, performance_metrics: Mapping[str, float]) -> None:
        """Adapt release weights based on drawdown and Sharpe observations."""

        drawdown = float(performance_metrics["drawdown"])
        sharpe = float(performance_metrics["sharpe"])
        cfg = self.config
        old_alpha = cfg["alpha"]
        old_beta = cfg["beta"]
        old_gamma = cfg["gamma"]
        c = math.exp(-self._tick_hours / cfg["mod_t_half"]) * (
            1.0 - math.exp(-self._tick_hours / cfg["mod_t_max"])
        )
        modulation = 1.0 + cfg["mod_k"] * c
        if drawdown < cfg["target_dd"]:
            cfg["alpha"] *= 1.01 * modulation
            cfg["gamma"] *= 1.01 * modulation
        if drawdown > cfg["target_dd"] and sharpe < cfg["target_sharpe"]:
            cfg["alpha"] *= 0.99 / modulation
            cfg["beta"] *= 0.99 / modulation
        if self._tacl_guard:
            proposal = {
                "alpha": cfg["alpha"],
                "beta": cfg["beta"],
                "gamma": cfg["gamma"],
                "drawdown": drawdown,
                "sharpe": sharpe,
                "modulation": modulation,
                "c": c,
            }
            if not self._tacl_guard("serotonin_meta_adapt", proposal):
                cfg["alpha"] = old_alpha
                cfg["beta"] = old_beta
                cfg["gamma"] = old_gamma
                return
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
            "phasic_level": float(self.phasic_level),
            "gate_level": float(self.gate_level),
            "alpha": float(self.config["alpha"]),
            "beta": float(self.config["beta"]),
            "gamma": float(self.config["gamma"]),
            "decay_rate": float(self.config["decay_rate"]),
        }
