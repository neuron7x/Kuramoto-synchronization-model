from __future__ import annotations

import math
from typing import Callable, Mapping, Optional

import yaml


class DopamineController:
    """DopamineController v2.1 — appetitive loop implementation.

    Implements TD(0) reward prediction error (RPE) with phasic and tonic
    dopamine dynamics, modulatory effects on action values and policy
    temperature, Go/No-Go gating, safe meta-adaptation, and TACL-compliant
    telemetry hooks.
    """

    # ---------- init / logging ----------

    def __init__(
        self,
        config_path: str = "config/dopamine.yaml",
        logger: Optional[Callable[[str, float], None]] = None,
    ) -> None:
        self.config_path = config_path
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)

        self.tonic_level: float = 0.0
        self.phasic_level: float = 0.0
        self.dopamine_level: float = 0.0
        self.value_estimate: float = 0.0
        self.last_rpe: float = 0.0

        self._logger = logger or self._default_logger

    def _default_logger(self, name: str, value: float) -> None:
        try:
            from tradepulse.runtime.thermo_api import log_metric  # type: ignore
        except ImportError:  # pragma: no cover - optional dependency.
            return
        try:
            log_metric(name, float(value))
        except Exception:  # pragma: no cover - safeguard against telemetry errors.
            pass

    def _log(self, name: str, value: float) -> None:
        try:
            self._logger(name, float(value))
        except Exception:  # pragma: no cover - defensive logging guard.
            pass

    # ---------- appetitive state ----------

    def estimate_appetitive_state(
        self,
        reward_proxy: float,
        novelty: float,
        momentum: float,
        value_gap: float,
        override_weights: Optional[Mapping[str, float]] = None,
    ) -> float:
        """Combine appetitive drivers into a non-negative scalar state."""

        if any(x < 0 for x in (reward_proxy, novelty, momentum, value_gap)):
            raise ValueError("reward_proxy, novelty, momentum, value_gap must be ≥ 0")

        cfg = self.config
        weights = override_weights or {}
        w_r = float(weights.get("w_r", cfg["w_r"]))
        w_n = float(weights.get("w_n", cfg["w_n"]))
        w_m = float(weights.get("w_m", cfg["w_m"]))
        w_v = float(weights.get("w_v", cfg["w_v"]))

        # optional novelty augmentation with |RPE|
        novelty_mode = str(cfg.get("novelty_mode", "external")).lower()
        if novelty_mode == "abs_rpe":
            novelty = novelty + float(cfg["c_absrpe"]) * abs(self.last_rpe)

        appetitive = w_r * reward_proxy + w_n * novelty + w_m * momentum + w_v * value_gap
        return float(max(0.0, appetitive))

    # ---------- TD(0) / RPE ----------

    def compute_rpe(
        self,
        reward: float,
        value: float,
        next_value: float,
        discount_gamma: Optional[float] = None,
    ) -> float:
        gamma = self.config["discount_gamma"] if discount_gamma is None else float(discount_gamma)
        rpe = float(reward + gamma * next_value - value)
        self.last_rpe = rpe
        return rpe

    def update_value_estimate(self, rpe: Optional[float] = None) -> float:
        if rpe is None:
            rpe = self.last_rpe
        lr = float(self.config["learning_rate_v"])
        old_v = self.value_estimate
        self.value_estimate = float(old_v + lr * rpe)
        self._log("dopamine_value_drift", self.value_estimate - old_v)
        return self.value_estimate

    # ---------- DA dynamics ----------

    def compute_dopamine_signal(
        self,
        appetitive_state: float,
        rpe: Optional[float] = None,
    ) -> float:
        if appetitive_state < 0:
            raise ValueError("appetitive_state must be ≥ 0")

        cfg = self.config
        rpe_val = self.last_rpe if rpe is None else float(rpe)

        # phasic component
        self.phasic_level = float(max(0.0, rpe_val) * cfg["burst_factor"])

        # tonic component via EMA
        decay = float(cfg["decay_rate"])
        ema_target = appetitive_state + self.phasic_level
        self.tonic_level = float((1.0 - decay) * self.tonic_level + decay * ema_target)

        # bounded logistic activation
        x = float(cfg["k"]) * (self.tonic_level - float(cfg["theta"]))
        x = max(min(x, 60.0), -60.0)
        sig = 1.0 / (1.0 + math.exp(-x))
        self.dopamine_level = float(sig)

        self._log("dopamine_tonic_level", self.tonic_level)
        self._log("dopamine_phasic_level", self.phasic_level)
        self._log("dopamine_level", self.dopamine_level)
        return self.dopamine_level

    # ---------- policy/value modulation ----------

    def modulate_action_value(
        self,
        original_value: float,
        dopamine_signal: Optional[float] = None,
        delta_gain: Optional[float] = None,
        baseline: Optional[float] = None,
    ) -> float:
        da = self.dopamine_level if dopamine_signal is None else float(dopamine_signal)
        dg = float(self.config["delta_gain"] if delta_gain is None else delta_gain)
        b = float(self.config["baseline"] if baseline is None else baseline)
        return float(original_value * (1.0 + dg * (da - b)))

    def compute_temperature(self, dopamine_signal: Optional[float] = None) -> float:
        da = self.dopamine_level if dopamine_signal is None else float(dopamine_signal)
        base = float(self.config["base_temperature"])
        tmin = float(self.config["min_temperature"])
        k_t = float(self.config["temp_k"])

        temp = base * math.exp(-k_t * da)

        # elevation under negative RPE for rapid exploration shifts
        neg_gain = float(self.config.get("neg_rpe_temp_gain", 0.5))
        max_mul = float(self.config.get("max_temp_multiplier", 3.0))
        if self.last_rpe < 0:
            temp *= min(max_mul, 1.0 + neg_gain * max(0.0, -self.last_rpe))

        temp = max(tmin, temp)
        self._log("dopamine_temperature", temp)
        return float(temp)

    def check_invigoration(self, dopamine_signal: Optional[float] = None) -> bool:
        da = self.dopamine_level if dopamine_signal is None else float(dopamine_signal)
        return bool(da > float(self.config["invigoration_threshold"]))

    def check_suppress(self, dopamine_signal: Optional[float] = None) -> bool:
        da = self.dopamine_level if dopamine_signal is None else float(dopamine_signal)
        return bool(da < float(self.config["no_go_threshold"]))

    # ---------- meta-adapt ----------

    def meta_adapt(self, performance_metrics: Mapping[str, float]) -> None:
        drawdown = float(performance_metrics["drawdown"])
        sharpe = float(performance_metrics["sharpe"])
        cfg = self.config

        good = (sharpe >= cfg["target_sharpe"]) and (drawdown >= cfg["target_dd"])
        bad = (sharpe < cfg["target_sharpe"]) and (drawdown < cfg["target_dd"])

        old_lr = float(cfg["learning_rate_v"])
        old_dg = float(cfg["delta_gain"])
        old_tb = float(cfg["base_temperature"])

        if good:
            cfg["learning_rate_v"] = float(old_lr * 1.01)
            cfg["delta_gain"] = float(old_dg * 1.01)
            cfg["base_temperature"] = float(old_tb * 0.99)
        elif bad:
            cfg["learning_rate_v"] = float(old_lr * 0.99)
            cfg["delta_gain"] = float(old_dg * 0.99)
            cfg["base_temperature"] = float(old_tb * 1.01)

        self._log("dopamine_lr_drift", float(cfg["learning_rate_v"]) - old_lr)
        self._log("dopamine_dg_drift", float(cfg["delta_gain"]) - old_dg)
        self._log("dopamine_temp_drift", float(cfg["base_temperature"]) - old_tb)
        self.save_config_to_yaml()

    # ---------- service ----------

    def update_metrics(self) -> None:
        self._log("dopamine_level", self.dopamine_level)
        self._log("dopamine_tonic_level", self.tonic_level)
        self._log("dopamine_phasic_level", self.phasic_level)
        self._log("dopamine_value_estimate", self.value_estimate)
        temp = self.compute_temperature()
        self._log("dopamine_temperature", temp)
        if temp > 0:
            self._log("dopamine_explore_exploit_ratio", 1.0 / float(temp))

    def save_config_to_yaml(self, path: Optional[str] = None) -> None:
        target = path or self.config_path
        with open(target, "w", encoding="utf-8") as f:
            yaml.safe_dump(self.config, f)

    def to_dict(self) -> dict[str, float | str]:
        return {
            "tonic_level": float(self.tonic_level),
            "phasic_level": float(self.phasic_level),
            "dopamine_level": float(self.dopamine_level),
            "value_estimate": float(self.value_estimate),
            "last_rpe": float(self.last_rpe),
            "discount_gamma": float(self.config["discount_gamma"]),
            "learning_rate_v": float(self.config["learning_rate_v"]),
            "delta_gain": float(self.config["delta_gain"]),
            "base_temperature": float(self.config["base_temperature"]),
            "novelty_mode": str(self.config.get("novelty_mode", "external")),
            "c_absrpe": float(self.config.get("c_absrpe", 0.1)),
        }
