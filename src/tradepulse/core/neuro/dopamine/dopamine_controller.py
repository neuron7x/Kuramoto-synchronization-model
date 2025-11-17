from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Dict, Mapping, Optional, Sequence, Tuple

import yaml

from ._invariants import check_monotonic_thresholds
from .ddm_adapter import DDMThresholds, ddm_thresholds


@dataclass(frozen=True)
class DopamineConfig:
    """Typed configuration with range validation and defaults."""

    version: str
    discount_gamma: float
    learning_rate_v: float
    decay_rate: float
    burst_factor: float
    k: float
    theta: float
    w_r: float
    w_n: float
    w_m: float
    w_v: float
    novelty_mode: str
    c_absrpe: float
    baseline: float
    delta_gain: float
    base_temperature: float
    min_temperature: float
    temp_k: float
    neg_rpe_temp_gain: float
    max_temp_multiplier: float
    invigoration_threshold: float
    no_go_threshold: float
    target_dd: float
    target_sharpe: float
    meta_cooldown_ticks: int
    metric_interval: int
    meta_adapt_rules: Dict[str, Mapping[str, float]]
    rpe_ema_beta: float
    temp_adapt_target_var: float
    temp_adapt_lr: float
    temp_adapt_beta1: float
    temp_adapt_beta2: float
    temp_adapt_epsilon: float
    temp_adapt_min_base: float
    temp_adapt_max_base: float
    rpe_var_release_threshold: float
    rpe_var_release_hysteresis: float
    ddm_temp_gain: float
    ddm_threshold_gain: float
    ddm_hold_gain: float
    ddm_min_temperature_scale: float
    ddm_max_temperature_scale: float
    ddm_baseline_a: float
    ddm_baseline_t0: float
    ddm_eps: float
    hold_threshold: float

    def to_mapping(self) -> Dict[str, float | str | int]:
        return {
            "version": self.version,
            "discount_gamma": self.discount_gamma,
            "learning_rate_v": self.learning_rate_v,
            "decay_rate": self.decay_rate,
            "burst_factor": self.burst_factor,
            "k": self.k,
            "theta": self.theta,
            "w_r": self.w_r,
            "w_n": self.w_n,
            "w_m": self.w_m,
            "w_v": self.w_v,
            "novelty_mode": self.novelty_mode,
            "c_absrpe": self.c_absrpe,
            "baseline": self.baseline,
            "delta_gain": self.delta_gain,
            "base_temperature": self.base_temperature,
            "min_temperature": self.min_temperature,
            "temp_k": self.temp_k,
            "neg_rpe_temp_gain": self.neg_rpe_temp_gain,
            "max_temp_multiplier": self.max_temp_multiplier,
            "invigoration_threshold": self.invigoration_threshold,
            "no_go_threshold": self.no_go_threshold,
            "target_dd": self.target_dd,
            "target_sharpe": self.target_sharpe,
            "meta_cooldown_ticks": self.meta_cooldown_ticks,
            "metric_interval": self.metric_interval,
            "meta_adapt_rules": self.meta_adapt_rules,
            "rpe_ema_beta": self.rpe_ema_beta,
            "temp_adapt_target_var": self.temp_adapt_target_var,
            "temp_adapt_lr": self.temp_adapt_lr,
            "temp_adapt_beta1": self.temp_adapt_beta1,
            "temp_adapt_beta2": self.temp_adapt_beta2,
            "temp_adapt_epsilon": self.temp_adapt_epsilon,
            "temp_adapt_min_base": self.temp_adapt_min_base,
            "temp_adapt_max_base": self.temp_adapt_max_base,
            "rpe_var_release_threshold": self.rpe_var_release_threshold,
            "rpe_var_release_hysteresis": self.rpe_var_release_hysteresis,
            "ddm_temp_gain": self.ddm_temp_gain,
            "ddm_threshold_gain": self.ddm_threshold_gain,
            "ddm_hold_gain": self.ddm_hold_gain,
            "ddm_min_temperature_scale": self.ddm_min_temperature_scale,
            "ddm_max_temperature_scale": self.ddm_max_temperature_scale,
            "ddm_baseline_a": self.ddm_baseline_a,
            "ddm_baseline_t0": self.ddm_baseline_t0,
            "ddm_eps": self.ddm_eps,
            "hold_threshold": self.hold_threshold,
        }


_DEFAULT_META_RULES: Dict[str, Mapping[str, float]] = {
    "good": {"learning_rate_v": 1.01, "delta_gain": 1.01, "base_temperature": 0.99},
    "bad": {"learning_rate_v": 0.99, "delta_gain": 0.99, "base_temperature": 1.01},
    "neutral": {
        "learning_rate_v": 1.0,
        "delta_gain": 1.0,
        "base_temperature": 1.0,
    },
}

_ALLOWED_NOVELTY_MODES = {"external", "abs_rpe"}


# Defaults for optional configuration keys. These mirror the canonical
# ``config/dopamine.yaml`` file but are inlined here so that lightweight test
# configurations can omit advanced meta-adaptation parameters.
_OPTIONAL_DEFAULTS: Dict[str, float] = {
    "rpe_ema_beta": 0.2,
    "temp_adapt_target_var": 0.12,
    "temp_adapt_lr": 0.05,
    "temp_adapt_beta1": 0.9,
    "temp_adapt_beta2": 0.999,
    "temp_adapt_epsilon": 1.0e-8,
    "temp_adapt_min_base": 0.2,
    "temp_adapt_max_base": 2.5,
    "rpe_var_release_threshold": 0.35,
    "rpe_var_release_hysteresis": 0.05,
    "ddm_temp_gain": 0.4,
    "ddm_threshold_gain": 0.3,
    "ddm_hold_gain": 0.6,
    "ddm_min_temperature_scale": 0.5,
    "ddm_max_temperature_scale": 2.0,
    "ddm_baseline_a": 1.0,
    "ddm_baseline_t0": 0.2,
    "ddm_eps": 1.0e-6,
    "hold_threshold": 0.4,
}


class DopamineController:
    """
    DopamineController v2.3 — апетитивний контур:
      • TD(0) RPE: δ = r + γ·V' − V (λ = 0) з насиченням γ.
      • Фазика: phasic = max(0, RPE)·burst_factor.
      • Тоніка: EMA(appetitive + phasic) з decay_rate.
      • DA: σ(k·(tonic − θ)), насичення логіту.
      • Q' = Q·(1 + delta_gain·(DA − baseline)).
      • T = clip(T_min, T_base·exp(−k_T·DA)·DDM_scale, T_base·max_mul).
      • Step() → (rpe, temperature, policy_logits, extras) з release_gate/telemetry.
      • Go / Hold / No-Go: дає анти-вибухові пороги + синхронізація з 5-HT HOLD.
      • Meta-adapt: Adam/EMA для температури на базі дисперсії RPE.
      • DDM адаптер: перетворює (v, a, t0) → temperature_scale та пороги.
      • Телеметрія: tacl.dopa.* + release gate (variance guard).
    """

    # ---------- init / logging ----------

    def __init__(
        self,
        config_path: str = "config/dopamine.yaml",
        logger: Optional[Callable[[str, float], None]] = None,
    ) -> None:
        self.config_path = config_path
        with open(config_path, "r", encoding="utf-8") as f:
            raw_cfg = yaml.safe_load(f)
        self._config_model = self._validate_config(raw_cfg)
        self.config: Dict[str, float | str | int | Mapping[str, float]] = dict(
            self._config_model.to_mapping()
        )
        self.config["meta_adapt_rules"] = {
            state: dict(rules)
            for state, rules in self.config["meta_adapt_rules"].items()
        }

        self.tonic_level: float = 0.0
        self.phasic_level: float = 0.0
        self.dopamine_level: float = 0.0
        self.value_estimate: float = 0.0
        self.last_rpe: float = 0.0
        self._meta_cooldown: int = int(self.config["meta_cooldown_ticks"])
        self._meta_cooldown_counter: int = 0
        self._metric_interval: int = int(self.config["metric_interval"])
        self._metric_counter: int = 0

        self._logger = logger or self._default_logger
        self._adaptive_base_temperature: float = float(self.config["base_temperature"])
        self._rpe_mean: float = 0.0
        self._rpe_sq_mean: float = 0.0
        self._temp_adam_m: float = 0.0
        self._temp_adam_v: float = 0.0
        self._temp_adam_t: int = 0
        self._release_gate_open: bool = True
        self._last_temperature: float = float(self.config["base_temperature"])

        # Cache frequently accessed config values for performance
        self._cache_discount_gamma: float = float(self.config["discount_gamma"])
        self._cache_learning_rate_v: float = float(self.config["learning_rate_v"])
        self._cache_decay_rate: float = float(self.config["decay_rate"])
        self._cache_burst_factor: float = float(self.config["burst_factor"])
        self._cache_k: float = float(self.config["k"])
        self._cache_theta: float = float(self.config["theta"])
        self._cache_min_temperature: float = float(self.config["min_temperature"])
        self._cache_temp_k: float = float(self.config["temp_k"])
        self._cache_max_temp_multiplier: float = float(
            self.config["max_temp_multiplier"]
        )
        self._cache_neg_rpe_temp_gain: float = float(
            self.config.get("neg_rpe_temp_gain", 0.5)
        )
        self._cache_rpe_ema_beta: float = float(self.config["rpe_ema_beta"])
        self._cache_invigoration_threshold: float = float(
            self.config["invigoration_threshold"]
        )
        self._cache_no_go_threshold: float = float(self.config["no_go_threshold"])
        self._cache_hold_threshold: float = float(self.config["hold_threshold"])

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

    @staticmethod
    def _ensure_finite(name: str, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError(f"{name} must be a finite number")
        return value

    # ---------- config validation ----------

    def _validate_config(self, raw_cfg: Mapping[str, object] | None) -> DopamineConfig:
        if raw_cfg is None:
            raise ValueError("DopamineController config file is empty")
        if not isinstance(raw_cfg, Mapping):
            raise ValueError("DopamineController config must be a mapping")

        allowed_keys = set(DopamineConfig.__annotations__.keys())
        unknown_keys = set(raw_cfg.keys()) - allowed_keys
        if unknown_keys:
            raise ValueError(f"Unknown dopamine config keys: {sorted(unknown_keys)}")

        def _require(key: str) -> object:
            if key in raw_cfg:
                return raw_cfg[key]
            if key in _OPTIONAL_DEFAULTS:
                return _OPTIONAL_DEFAULTS[key]
            raise ValueError(f"Missing required dopamine config key: {key}")

        version = str(_require("version"))
        discount_gamma = float(_require("discount_gamma"))
        learning_rate_v = float(_require("learning_rate_v"))
        decay_rate = float(_require("decay_rate"))
        burst_factor = float(_require("burst_factor"))
        k_val = float(_require("k"))
        theta_val = float(_require("theta"))
        w_r = float(_require("w_r"))
        w_n = float(_require("w_n"))
        w_m = float(_require("w_m"))
        w_v = float(_require("w_v"))
        novelty_mode = str(_require("novelty_mode")).lower()
        c_absrpe = float(_require("c_absrpe"))
        baseline = float(_require("baseline"))
        delta_gain = float(_require("delta_gain"))
        base_temperature = float(_require("base_temperature"))
        min_temperature = float(_require("min_temperature"))
        temp_k = float(_require("temp_k"))
        neg_rpe_temp_gain = float(_require("neg_rpe_temp_gain"))
        max_temp_multiplier = float(_require("max_temp_multiplier"))
        invigoration_threshold = float(_require("invigoration_threshold"))
        no_go_threshold = float(_require("no_go_threshold"))
        target_dd = float(_require("target_dd"))
        target_sharpe = float(_require("target_sharpe"))
        meta_cooldown_ticks = int(_require("meta_cooldown_ticks"))
        metric_interval = int(_require("metric_interval"))
        meta_rules_raw = raw_cfg.get("meta_adapt_rules", _DEFAULT_META_RULES)
        rpe_ema_beta = float(_require("rpe_ema_beta"))
        temp_adapt_target_var = float(_require("temp_adapt_target_var"))
        temp_adapt_lr = float(_require("temp_adapt_lr"))
        temp_adapt_beta1 = float(_require("temp_adapt_beta1"))
        temp_adapt_beta2 = float(_require("temp_adapt_beta2"))
        temp_adapt_epsilon = float(_require("temp_adapt_epsilon"))
        temp_adapt_min_base = float(_require("temp_adapt_min_base"))
        temp_adapt_max_base = float(_require("temp_adapt_max_base"))
        rpe_var_release_threshold = float(_require("rpe_var_release_threshold"))
        rpe_var_release_hysteresis = float(_require("rpe_var_release_hysteresis"))
        ddm_temp_gain = float(_require("ddm_temp_gain"))
        ddm_threshold_gain = float(_require("ddm_threshold_gain"))
        ddm_hold_gain = float(_require("ddm_hold_gain"))
        ddm_min_temperature_scale = float(_require("ddm_min_temperature_scale"))
        ddm_max_temperature_scale = float(_require("ddm_max_temperature_scale"))
        ddm_baseline_a = float(_require("ddm_baseline_a"))
        ddm_baseline_t0 = float(_require("ddm_baseline_t0"))
        ddm_eps = float(_require("ddm_eps"))
        hold_threshold = float(_require("hold_threshold"))

        if not math.isfinite(discount_gamma) or not (0.0 < discount_gamma <= 1.0):
            raise ValueError("discount_gamma must be in (0, 1]")
        if not math.isfinite(learning_rate_v) or not (0.0 < learning_rate_v <= 1.0):
            raise ValueError("learning_rate_v must be in (0, 1]")
        if not math.isfinite(decay_rate) or not (0.0 <= decay_rate <= 1.0):
            raise ValueError("decay_rate must be in [0, 1]")
        if burst_factor < 0.0 or not math.isfinite(burst_factor):
            raise ValueError("burst_factor must be ≥ 0")
        if not math.isfinite(k_val) or k_val == 0.0:
            raise ValueError("k must be non-zero and finite")
        if not math.isfinite(theta_val):
            raise ValueError("theta must be finite")
        for weight_value, label in (
            (w_r, "w_r"),
            (w_n, "w_n"),
            (w_m, "w_m"),
            (w_v, "w_v"),
        ):
            if not math.isfinite(weight_value) or weight_value < 0.0:
                raise ValueError(f"{label} must be ≥ 0")
        if novelty_mode not in _ALLOWED_NOVELTY_MODES:
            raise ValueError(f"novelty_mode must be one of {_ALLOWED_NOVELTY_MODES}")
        if c_absrpe < 0.0 or not math.isfinite(c_absrpe):
            raise ValueError("c_absrpe must be ≥ 0")
        if not 0.0 <= baseline <= 1.0:
            raise ValueError("baseline must be within [0, 1]")
        if not 0.0 <= delta_gain <= 1.0:
            raise ValueError("delta_gain must be within [0, 1]")
        if base_temperature <= 0.0 or not math.isfinite(base_temperature):
            raise ValueError("base_temperature must be > 0")
        if min_temperature <= 0.0 or not math.isfinite(min_temperature):
            raise ValueError("min_temperature must be > 0")
        if min_temperature > base_temperature:
            raise ValueError("min_temperature must be ≤ base_temperature")
        if temp_k <= 0.0 or not math.isfinite(temp_k):
            raise ValueError("temp_k must be > 0")
        if neg_rpe_temp_gain < 0.0 or not math.isfinite(neg_rpe_temp_gain):
            raise ValueError("neg_rpe_temp_gain must be ≥ 0")
        if max_temp_multiplier < 1.0 or not math.isfinite(max_temp_multiplier):
            raise ValueError("max_temp_multiplier must be ≥ 1")
        if not 0.0 <= invigoration_threshold <= 1.0:
            raise ValueError("invigoration_threshold must be within [0, 1]")
        if not 0.0 <= no_go_threshold <= 1.0:
            raise ValueError("no_go_threshold must be within [0, 1]")
        if meta_cooldown_ticks < 0:
            raise ValueError("meta_cooldown_ticks must be ≥ 0")
        if metric_interval <= 0:
            raise ValueError("metric_interval must be ≥ 1")
        if target_sharpe <= 0.0 or not math.isfinite(target_sharpe):
            raise ValueError("target_sharpe must be > 0")

        if not isinstance(meta_rules_raw, Mapping):
            raise ValueError("meta_adapt_rules must be a mapping")

        if not 0.0 < rpe_ema_beta <= 1.0:
            raise ValueError("rpe_ema_beta must be in (0, 1]")
        if temp_adapt_target_var < 0.0 or not math.isfinite(temp_adapt_target_var):
            raise ValueError("temp_adapt_target_var must be ≥ 0")
        if temp_adapt_lr <= 0.0 or not math.isfinite(temp_adapt_lr):
            raise ValueError("temp_adapt_lr must be > 0")
        if not 0.0 < temp_adapt_beta1 < 1.0:
            raise ValueError("temp_adapt_beta1 must be in (0, 1)")
        if not 0.0 < temp_adapt_beta2 < 1.0:
            raise ValueError("temp_adapt_beta2 must be in (0, 1)")
        if temp_adapt_epsilon <= 0.0 or not math.isfinite(temp_adapt_epsilon):
            raise ValueError("temp_adapt_epsilon must be > 0")
        if temp_adapt_min_base <= 0.0 or not math.isfinite(temp_adapt_min_base):
            raise ValueError("temp_adapt_min_base must be > 0")
        if temp_adapt_max_base <= 0.0 or not math.isfinite(temp_adapt_max_base):
            raise ValueError("temp_adapt_max_base must be > 0")
        if temp_adapt_min_base > temp_adapt_max_base:
            raise ValueError("temp_adapt_min_base must be ≤ temp_adapt_max_base")
        if rpe_var_release_threshold < 0.0 or not math.isfinite(
            rpe_var_release_threshold
        ):
            raise ValueError("rpe_var_release_threshold must be ≥ 0")
        if rpe_var_release_hysteresis < 0.0 or not math.isfinite(
            rpe_var_release_hysteresis
        ):
            raise ValueError("rpe_var_release_hysteresis must be ≥ 0")
        if ddm_temp_gain < 0.0 or not math.isfinite(ddm_temp_gain):
            raise ValueError("ddm_temp_gain must be ≥ 0")
        if ddm_threshold_gain < 0.0 or not math.isfinite(ddm_threshold_gain):
            raise ValueError("ddm_threshold_gain must be ≥ 0")
        if ddm_hold_gain < 0.0 or not math.isfinite(ddm_hold_gain):
            raise ValueError("ddm_hold_gain must be ≥ 0")
        if ddm_min_temperature_scale <= 0.0 or not math.isfinite(
            ddm_min_temperature_scale
        ):
            raise ValueError("ddm_min_temperature_scale must be > 0")
        if ddm_max_temperature_scale <= 0.0 or not math.isfinite(
            ddm_max_temperature_scale
        ):
            raise ValueError("ddm_max_temperature_scale must be > 0")
        if ddm_min_temperature_scale > ddm_max_temperature_scale:
            raise ValueError(
                "ddm_min_temperature_scale must be ≤ ddm_max_temperature_scale"
            )
        if ddm_baseline_a <= 0.0 or not math.isfinite(ddm_baseline_a):
            raise ValueError("ddm_baseline_a must be > 0")
        if ddm_baseline_t0 < 0.0 or not math.isfinite(ddm_baseline_t0):
            raise ValueError("ddm_baseline_t0 must be ≥ 0")
        if ddm_eps <= 0.0 or not math.isfinite(ddm_eps):
            raise ValueError("ddm_eps must be > 0")
        if not 0.0 <= hold_threshold <= 1.0:
            raise ValueError("hold_threshold must be within [0, 1]")

        meta_rules: Dict[str, Mapping[str, float]] = {}
        for state in ("good", "bad", "neutral"):
            state_rules = meta_rules_raw.get(state, _DEFAULT_META_RULES[state])
            if not isinstance(state_rules, Mapping):
                raise ValueError(f"meta_adapt_rules[{state}] must be a mapping")
            validated: Dict[str, float] = {}
            for key in ("learning_rate_v", "delta_gain", "base_temperature"):
                if key not in state_rules:
                    raise ValueError(f"meta_adapt_rules[{state}] missing {key}")
                value = float(state_rules[key])
                if not math.isfinite(value):
                    raise ValueError(f"meta_adapt_rules[{state}][{key}] must be finite")
                validated[key] = value
            meta_rules[state] = validated

        return DopamineConfig(
            version=version,
            discount_gamma=discount_gamma,
            learning_rate_v=learning_rate_v,
            decay_rate=decay_rate,
            burst_factor=burst_factor,
            k=k_val,
            theta=theta_val,
            w_r=w_r,
            w_n=w_n,
            w_m=w_m,
            w_v=w_v,
            novelty_mode=novelty_mode,
            c_absrpe=c_absrpe,
            baseline=baseline,
            delta_gain=delta_gain,
            base_temperature=base_temperature,
            min_temperature=min_temperature,
            temp_k=temp_k,
            neg_rpe_temp_gain=neg_rpe_temp_gain,
            max_temp_multiplier=max_temp_multiplier,
            invigoration_threshold=invigoration_threshold,
            no_go_threshold=no_go_threshold,
            target_dd=target_dd,
            target_sharpe=target_sharpe,
            meta_cooldown_ticks=meta_cooldown_ticks,
            metric_interval=metric_interval,
            meta_adapt_rules=meta_rules,
            rpe_ema_beta=rpe_ema_beta,
            temp_adapt_target_var=temp_adapt_target_var,
            temp_adapt_lr=temp_adapt_lr,
            temp_adapt_beta1=temp_adapt_beta1,
            temp_adapt_beta2=temp_adapt_beta2,
            temp_adapt_epsilon=temp_adapt_epsilon,
            temp_adapt_min_base=temp_adapt_min_base,
            temp_adapt_max_base=temp_adapt_max_base,
            rpe_var_release_threshold=rpe_var_release_threshold,
            rpe_var_release_hysteresis=rpe_var_release_hysteresis,
            ddm_temp_gain=ddm_temp_gain,
            ddm_threshold_gain=ddm_threshold_gain,
            ddm_hold_gain=ddm_hold_gain,
            ddm_min_temperature_scale=ddm_min_temperature_scale,
            ddm_max_temperature_scale=ddm_max_temperature_scale,
            ddm_baseline_a=ddm_baseline_a,
            ddm_baseline_t0=ddm_baseline_t0,
            ddm_eps=ddm_eps,
            hold_threshold=hold_threshold,
        )

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

        reward_proxy = self._ensure_finite("reward_proxy", float(reward_proxy))
        novelty = self._ensure_finite("novelty", float(novelty))
        momentum = self._ensure_finite("momentum", float(momentum))
        value_gap = self._ensure_finite("value_gap", float(value_gap))

        cfg = self.config
        weights = override_weights or {}
        w_r = float(weights.get("w_r", cfg["w_r"]))
        w_n = float(weights.get("w_n", cfg["w_n"]))
        w_m = float(weights.get("w_m", cfg["w_m"]))
        w_v = float(weights.get("w_v", cfg["w_v"]))

        # опціональна новизна з |RPE|
        novelty_mode = str(cfg.get("novelty_mode", "external")).lower()
        if novelty_mode == "abs_rpe":
            novelty = novelty + float(cfg["c_absrpe"]) * abs(self.last_rpe)

        appetitive = (
            w_r * reward_proxy + w_n * novelty + w_m * momentum + w_v * value_gap
        )
        return float(max(0.0, appetitive))

    # ---------- TD(0) / RPE ----------

    def compute_rpe(
        self,
        reward: float,
        value: float,
        next_value: float,
        discount_gamma: Optional[float] = None,
    ) -> float:
        """Compute TD(0) reward prediction error: δ = r + γ·V' − V.

        Args:
            reward: Observed reward
            value: Current state value estimate V
            next_value: Next state value estimate V'
            discount_gamma: Optional discount factor override (must be in (0,1])

        Returns:
            RPE δ

        Raises:
            RuntimeError: If any input or computed value is NaN or ±Inf
            ValueError: If discount_gamma is not in (0, 1]
        """
        reward = self._ensure_finite("reward", float(reward))
        value = self._ensure_finite("value", float(value))
        next_value = self._ensure_finite("next_value", float(next_value))
        gamma = (
            self._cache_discount_gamma
            if discount_gamma is None
            else float(discount_gamma)
        )
        self._ensure_finite("discount_gamma", gamma)

        # Strict gamma validation as per spec: γ ∈ (0, 1]
        if not (0.0 < gamma <= 1.0):
            raise ValueError(f"discount_gamma must be in (0, 1], got {gamma}")

        # Compute RPE with overflow protection
        try:
            rpe = float(reward + gamma * next_value - value)
        except (OverflowError, FloatingPointError) as e:
            context = {
                "reward": reward,
                "value": value,
                "next_value": next_value,
                "gamma": gamma,
            }
            raise RuntimeError(
                f"RPE computation overflow: {e}\nContext: {context}"
            ) from e

        # Final NaN/Inf check with context
        if not math.isfinite(rpe):
            context = {
                "reward": reward,
                "value": value,
                "next_value": next_value,
                "gamma": gamma,
                "rpe": rpe,
            }
            raise RuntimeError(
                f"RPE computation produced non-finite value: {rpe}\nContext: {context}"
            )

        self.last_rpe = rpe
        return rpe

    def update_value_estimate(self, rpe: Optional[float] = None) -> float:
        if rpe is None:
            rpe = self.last_rpe
        rpe = self._ensure_finite("rpe", float(rpe))
        lr = self._cache_learning_rate_v
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
        appetitive_state = self._ensure_finite(
            "appetitive_state", float(appetitive_state)
        )

        rpe_val = self.last_rpe if rpe is None else float(rpe)
        rpe_val = self._ensure_finite("rpe", rpe_val)

        # phasic
        self.phasic_level = float(max(0.0, rpe_val) * self._cache_burst_factor)

        # tonic (EMA)
        self.tonic_level = float(
            (1.0 - self._cache_decay_rate) * self.tonic_level
            + self._cache_decay_rate * (appetitive_state + self.phasic_level)
        )
        self._ensure_finite("tonic_level", self.tonic_level)

        # bounded logistic
        x = self._cache_k * (self.tonic_level - self._cache_theta)
        x = max(min(x, 60.0), -60.0)
        sig = 1.0 / (1.0 + math.exp(-x))
        self.dopamine_level = float(min(1.0, max(0.0, sig)))

        self._log("dopamine_tonic_level", self.tonic_level)
        self._log("dopamine_phasic_level", self.phasic_level)
        self._log("dopamine_level", self.dopamine_level)
        return self.dopamine_level

    def step(
        self,
        reward: float,
        value: float,
        next_value: float,
        appetitive_state: float,
        policy_logits: Optional[Sequence[float]] = None,
        *,
        ddm_params: Optional[Tuple[float, float, float]] = None,
        discount_gamma: Optional[float] = None,
    ) -> Tuple[float, float, Tuple[float, ...], Mapping[str, object]]:
        rpe = self.compute_rpe(reward, value, next_value, discount_gamma=discount_gamma)
        self.update_value_estimate(rpe)
        variance = self._update_rpe_statistics(rpe)
        adaptive_base = self._meta_adapt_temperature(variance)
        release_gate = self._update_release_gate(variance)

        dopamine_signal = self.compute_dopamine_signal(appetitive_state, rpe)
        temperature = self.compute_temperature(
            dopamine_signal, base_temperature=adaptive_base
        )

        ddm_info: Optional[DDMThresholds] = None
        if ddm_params is not None:
            v, a, t0 = ddm_params
            ddm_info = ddm_thresholds(
                v,
                a,
                t0,
                temp_gain=float(self.config["ddm_temp_gain"]),
                threshold_gain=float(self.config["ddm_threshold_gain"]),
                hold_gain=float(self.config["ddm_hold_gain"]),
                min_temp_scale=float(self.config["ddm_min_temperature_scale"]),
                max_temp_scale=float(self.config["ddm_max_temperature_scale"]),
                baseline_a=float(self.config["ddm_baseline_a"]),
                baseline_t0=float(self.config["ddm_baseline_t0"]),
                eps=float(self.config["ddm_eps"]),
            )
            temperature *= ddm_info.temperature_scale
            t_bounds = self.temperature_bounds()
            temperature = min(t_bounds[1], max(t_bounds[0], temperature))

        self._last_temperature = temperature

        go_threshold = self._cache_invigoration_threshold
        no_go_threshold = self._cache_no_go_threshold
        hold_threshold = self._cache_hold_threshold
        if ddm_info is not None:
            go_threshold = ddm_info.go_threshold
            no_go_threshold = ddm_info.no_go_threshold
            hold_threshold = ddm_info.hold_threshold

        # Ensure monotonic constraint: go >= hold >= no_go
        # This implements fail-shut: if thresholds are inconsistent, they're adjusted
        go_threshold, hold_threshold, no_go_threshold = check_monotonic_thresholds(
            go_threshold, hold_threshold, no_go_threshold
        )

        hold_gate = (not release_gate) or dopamine_signal < hold_threshold
        go_gate = dopamine_signal > go_threshold and not hold_gate
        no_go_gate = hold_gate or dopamine_signal < no_go_threshold

        scaled_policy: Tuple[float, ...]
        if policy_logits is None:
            scaled_policy = tuple()
        else:
            scaled_policy = tuple(
                self.modulate_action_value(logit, dopamine_signal=dopamine_signal)
                for logit in policy_logits
            )

        # Comprehensive extras export as per production spec
        extras: Dict[str, object] = {
            # Core DA signals
            "dopamine_level": dopamine_signal,
            "da_tonic": self.tonic_level,
            "da_phasic": self.phasic_level,
            # RPE & value
            "rpe": rpe,
            "rpe_var": variance,
            "value_estimate": self.value_estimate,
            # Temperature
            "temperature": temperature,
            "adaptive_base_temperature": adaptive_base,
            # Gate state
            "go": go_gate,
            "hold": hold_gate,
            "no_go": no_go_gate,
            # Thresholds
            "go_threshold": go_threshold,
            "hold_threshold": hold_threshold,
            "no_go_threshold": no_go_threshold,
            # Release gate
            "release_gate_open": release_gate,
        }
        if ddm_info is not None:
            extras["ddm_thresholds"] = ddm_info
            extras["ddm_scale"] = ddm_info.temperature_scale

        # TACL telemetry logging
        self._log("tacl.dopa.level", dopamine_signal)
        self._log("tacl.dopa.tonic", self.tonic_level)
        self._log("tacl.dopa.phasic", self.phasic_level)
        self._log("tacl.dopa.rpe", rpe)
        self._log("tacl.dopa.rpe_var", variance)
        self._log("tacl.dopa.temp", temperature)
        self._log("tacl.dopa.go", 1.0 if go_gate else 0.0)
        self._log("tacl.dopa.hold", 1.0 if hold_gate else 0.0)
        self._log("tacl.dopa.no_go", 1.0 if no_go_gate else 0.0)
        if ddm_info is not None:
            self._log("tacl.dopa.ddm.scale", ddm_info.temperature_scale)
            self._log("tacl.dopa.ddm.go", ddm_info.go_threshold)
            self._log("tacl.dopa.ddm.hold", ddm_info.hold_threshold)
            self._log("tacl.dopa.ddm.no_go", ddm_info.no_go_threshold)
        self._log("dopamine_release_gate", 1.0 if release_gate else 0.0)

        return rpe, temperature, scaled_policy, extras

    def _update_rpe_statistics(self, rpe: float) -> float:
        beta = self._cache_rpe_ema_beta
        self._rpe_mean = (1.0 - beta) * self._rpe_mean + beta * rpe
        self._rpe_sq_mean = (1.0 - beta) * self._rpe_sq_mean + beta * (rpe * rpe)
        variance = max(0.0, self._rpe_sq_mean - self._rpe_mean * self._rpe_mean)
        self._log("dopamine_rpe_variance", variance)
        return variance

    def _meta_adapt_temperature(self, variance: float) -> float:
        lr = float(self.config["temp_adapt_lr"])
        beta1 = float(self.config["temp_adapt_beta1"])
        beta2 = float(self.config["temp_adapt_beta2"])
        eps = float(self.config["temp_adapt_epsilon"])
        target = float(self.config["temp_adapt_target_var"])

        gradient = variance - target
        self._temp_adam_t += 1
        self._temp_adam_m = beta1 * self._temp_adam_m + (1.0 - beta1) * gradient
        self._temp_adam_v = beta2 * self._temp_adam_v + (1.0 - beta2) * (
            gradient * gradient
        )
        bias_correction_m = 1.0 - beta1**self._temp_adam_t
        bias_correction_v = 1.0 - beta2**self._temp_adam_t
        m_hat = (
            self._temp_adam_m / bias_correction_m if bias_correction_m != 0.0 else 0.0
        )
        v_hat = (
            self._temp_adam_v / bias_correction_v if bias_correction_v != 0.0 else 0.0
        )
        step = lr * m_hat / (math.sqrt(v_hat) + eps)
        candidate = self._adaptive_base_temperature + step
        min_base = float(self.config["temp_adapt_min_base"])
        max_base = float(self.config["temp_adapt_max_base"])
        self._adaptive_base_temperature = float(min(max_base, max(min_base, candidate)))
        self.config["base_temperature"] = self._adaptive_base_temperature
        self._log("dopamine_meta_temp_base", self._adaptive_base_temperature)
        return self._adaptive_base_temperature

    def _update_release_gate(self, variance: float) -> bool:
        threshold = float(self.config["rpe_var_release_threshold"])
        hysteresis = float(self.config["rpe_var_release_hysteresis"])
        if variance > threshold:
            self._release_gate_open = False
        elif variance < max(0.0, threshold - hysteresis):
            self._release_gate_open = True
        return self._release_gate_open

    # ---------- policy/value modulation ----------

    def modulate_action_value(
        self,
        original_value: float,
        dopamine_signal: Optional[float] = None,
        delta_gain: Optional[float] = None,
        baseline: Optional[float] = None,
    ) -> float:
        da = self.dopamine_level if dopamine_signal is None else float(dopamine_signal)
        da = self._ensure_finite("dopamine_signal", da)
        dg = float(self.config["delta_gain"] if delta_gain is None else delta_gain)
        b = float(self.config["baseline"] if baseline is None else baseline)
        original_value = self._ensure_finite("original_value", float(original_value))
        result = float(original_value * (1.0 + dg * (da - b)))
        return result

    def compute_temperature(
        self,
        dopamine_signal: Optional[float] = None,
        base_temperature: Optional[float] = None,
    ) -> float:
        da = self.dopamine_level if dopamine_signal is None else float(dopamine_signal)
        da = self._ensure_finite("dopamine_signal", da)
        base = (
            self._adaptive_base_temperature
            if base_temperature is None
            else float(base_temperature)
        )
        tmin = self._cache_min_temperature
        k_t = self._cache_temp_k

        temp = base * math.exp(-k_t * da)

        # підвищення температури при негативному RPE (швидкий перехід до exploration)
        neg_gain = self._cache_neg_rpe_temp_gain
        max_mul = self._cache_max_temp_multiplier
        if self.last_rpe < 0:
            temp *= min(max_mul, 1.0 + neg_gain * max(0.0, -self.last_rpe))

        temp = max(tmin, temp)
        temp = min(temp, base * max_mul)
        if not math.isfinite(temp):
            raise ValueError("Temperature calculation produced a non-finite value")
        self._last_temperature = temp
        self._log("dopamine_temperature", temp)
        return float(temp)

    def check_invigoration(self, dopamine_signal: Optional[float] = None) -> bool:
        da = self.dopamine_level if dopamine_signal is None else float(dopamine_signal)
        da = min(1.0, max(0.0, da))
        return bool(da > self._cache_invigoration_threshold)

    def check_suppress(self, dopamine_signal: Optional[float] = None) -> bool:
        da = self.dopamine_level if dopamine_signal is None else float(dopamine_signal)
        da = min(1.0, max(0.0, da))
        return bool(da < self._cache_no_go_threshold)

    def temperature_bounds(self) -> Tuple[float, float]:
        base = self._adaptive_base_temperature
        tmin = self._cache_min_temperature
        return (tmin, base * self._cache_max_temp_multiplier)

    # ---------- meta-adapt ----------

    def meta_adapt(self, performance_metrics: Mapping[str, float]) -> None:
        drawdown = self._ensure_finite(
            "drawdown", float(performance_metrics["drawdown"])
        )
        sharpe = self._ensure_finite("sharpe", float(performance_metrics["sharpe"]))
        cfg = self.config

        good = (sharpe >= cfg["target_sharpe"]) and (drawdown >= cfg["target_dd"])
        bad = (sharpe < cfg["target_sharpe"]) and (drawdown < cfg["target_dd"])
        state = "neutral"
        if good:
            state = "good"
        elif bad:
            state = "bad"

        if self._meta_cooldown_counter > 0 and state != "neutral":
            self._meta_cooldown_counter -= 1
            self._log("dopamine_meta_skip", float(self._meta_cooldown_counter))
            return

        rules = cfg["meta_adapt_rules"][state]

        for key, factor in rules.items():
            old_value = float(cfg[key])
            new_value = float(old_value * factor)
            cfg[key] = new_value
            if key == "base_temperature":
                self._adaptive_base_temperature = new_value
            self._log(f"dopamine_meta_{key}", new_value - old_value)

        self._log("dopamine_meta_state", {"good": 1.0, "bad": -1.0}.get(state, 0.0))
        if state != "neutral" and self._meta_cooldown > 0:
            self._meta_cooldown_counter = self._meta_cooldown

        self.save_config_to_yaml()

    # ---------- service ----------

    def update_metrics(self) -> None:
        self._metric_interval = max(
            1, int(self.config.get("metric_interval", self._metric_interval))
        )
        self._metric_counter = (self._metric_counter + 1) % self._metric_interval
        if self._metric_counter != 0:
            return

        self._log("dopamine_level", self.dopamine_level)
        self._log("dopamine_tonic_level", self.tonic_level)
        self._log("dopamine_phasic_level", self.phasic_level)
        self._log("dopamine_value_estimate", self.value_estimate)
        t = self.compute_temperature()
        self._log("dopamine_temperature", t)
        if t > 0:
            self._log("dopamine_explore_exploit_ratio", 1.0 / float(t))

    def save_config_to_yaml(self, path: Optional[str] = None) -> None:
        target = path or self.config_path
        serialisable_cfg = dict(self.config)
        serialisable_cfg["meta_adapt_rules"] = {
            state: dict(rules)
            for state, rules in serialisable_cfg["meta_adapt_rules"].items()
        }
        with open(target, "w", encoding="utf-8") as f:
            yaml.safe_dump(serialisable_cfg, f)

    def to_dict(self) -> dict:
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
            "version": str(self.config.get("version", "unknown")),
            "adaptive_base_temperature": float(self._adaptive_base_temperature),
            "rpe_mean": float(self._rpe_mean),
            "rpe_variance": float(
                max(0.0, self._rpe_sq_mean - self._rpe_mean * self._rpe_mean)
            ),
            "temperature": float(self._last_temperature),
        }

    def reset_state(self) -> None:
        self.tonic_level = 0.0
        self.phasic_level = 0.0
        self.dopamine_level = 0.0
        self.value_estimate = 0.0
        self.last_rpe = 0.0
        self._rpe_mean = 0.0
        self._rpe_sq_mean = 0.0
        self._temp_adam_m = 0.0
        self._temp_adam_v = 0.0
        self._temp_adam_t = 0
        self._release_gate_open = True
        self._adaptive_base_temperature = float(self.config["base_temperature"])
        self._last_temperature = float(self.config["base_temperature"])

    def dump_state(self) -> Mapping[str, float]:
        return {
            "tonic_level": self.tonic_level,
            "phasic_level": self.phasic_level,
            "dopamine_level": self.dopamine_level,
            "value_estimate": self.value_estimate,
            "last_rpe": self.last_rpe,
            "adaptive_base_temperature": self._adaptive_base_temperature,
            "rpe_mean": self._rpe_mean,
            "rpe_sq_mean": self._rpe_sq_mean,
            "temp_adam_m": self._temp_adam_m,
            "temp_adam_v": self._temp_adam_v,
            "temp_adam_t": float(self._temp_adam_t),
            "release_gate_open": float(1.0 if self._release_gate_open else 0.0),
            "last_temperature": self._last_temperature,
        }

    def load_state(self, state: Mapping[str, float]) -> None:
        required_keys = {
            "tonic_level",
            "phasic_level",
            "dopamine_level",
            "value_estimate",
            "last_rpe",
            "adaptive_base_temperature",
            "rpe_mean",
            "rpe_sq_mean",
            "temp_adam_m",
            "temp_adam_v",
            "temp_adam_t",
            "release_gate_open",
            "last_temperature",
        }
        missing = required_keys - set(state.keys())
        if missing:
            raise ValueError(f"State missing keys: {sorted(missing)}")
        self.tonic_level = self._ensure_finite(
            "tonic_level", float(state["tonic_level"])
        )
        self.phasic_level = self._ensure_finite(
            "phasic_level", float(state["phasic_level"])
        )
        self.dopamine_level = min(
            1.0,
            max(
                0.0,
                self._ensure_finite("dopamine_level", float(state["dopamine_level"])),
            ),
        )
        self.value_estimate = self._ensure_finite(
            "value_estimate", float(state["value_estimate"])
        )
        self.last_rpe = self._ensure_finite("last_rpe", float(state["last_rpe"]))
        self._adaptive_base_temperature = self._ensure_finite(
            "adaptive_base_temperature", float(state["adaptive_base_temperature"])
        )
        self.config["base_temperature"] = self._adaptive_base_temperature
        self._rpe_mean = self._ensure_finite("rpe_mean", float(state["rpe_mean"]))
        self._rpe_sq_mean = self._ensure_finite(
            "rpe_sq_mean", float(state["rpe_sq_mean"])
        )
        self._temp_adam_m = self._ensure_finite(
            "temp_adam_m", float(state["temp_adam_m"])
        )
        self._temp_adam_v = self._ensure_finite(
            "temp_adam_v", float(state["temp_adam_v"])
        )
        temp_adam_t = int(
            round(self._ensure_finite("temp_adam_t", float(state["temp_adam_t"])))
        )
        self._temp_adam_t = max(0, temp_adam_t)
        release_flag = self._ensure_finite(
            "release_gate_open", float(state["release_gate_open"])
        )
        self._release_gate_open = bool(release_flag >= 0.5)
        self._last_temperature = self._ensure_finite(
            "last_temperature", float(state["last_temperature"])
        )
