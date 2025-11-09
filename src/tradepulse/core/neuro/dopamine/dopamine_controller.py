from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Dict, Mapping, Optional

import yaml


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


class DopamineController:
    """
    DopamineController v2.1 — апетитивний контур:
      • TD(0) RPE: δ = r + γ·V' − V
      • Фазика: phasic = max(0, RPE)·burst_factor
      • Тоніка: EMA(appetitive + phasic) з decay_rate
      • DA: σ(k·(tonic − θ)), насичення логіту
      • Q' = Q·(1 + delta_gain·(DA − baseline))
      • T = max(T_min, T_base·exp(−k_T·DA)) із підвищенням при негативному RPE
      • Go / No-Go: DA > invigoration_threshold / DA < no_go_threshold
      • Мета-адаптація: дріфт lr/delta_gain/base_temperature за DD/Sharpe
      • Телеметрія: сумісна з TACL log_metric, безпечні no-op фоли
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
        self.tonic_to_phasic_ratio: float = 0.0
        self.value_estimate: float = 0.0
        self.last_rpe: float = 0.0
        self._meta_cooldown: int = int(self.config["meta_cooldown_ticks"])
        self._meta_cooldown_counter: int = 0
        self._metric_interval: int = int(self.config["metric_interval"])
        self._metric_counter: int = 0

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
            if key not in raw_cfg:
                raise ValueError(f"Missing required dopamine config key: {key}")
            return raw_cfg[key]

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
        for weight_value, label in ((w_r, "w_r"), (w_n, "w_n"), (w_m, "w_m"), (w_v, "w_v")):
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
                    raise ValueError(
                        f"meta_adapt_rules[{state}][{key}] must be finite"
                    )
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
        reward = self._ensure_finite("reward", float(reward))
        value = self._ensure_finite("value", float(value))
        next_value = self._ensure_finite("next_value", float(next_value))
        gamma = (
            float(self.config["discount_gamma"]) if discount_gamma is None else float(discount_gamma)
        )
        self._ensure_finite("discount_gamma", gamma)
        if not (0.0 <= gamma <= 1.0):
            raise ValueError("discount_gamma must stay within [0, 1]")
        rpe = float(reward + gamma * next_value - value)
        self.last_rpe = rpe
        return rpe

    def update_value_estimate(self, rpe: Optional[float] = None) -> float:
        if rpe is None:
            rpe = self.last_rpe
        rpe = self._ensure_finite("rpe", float(rpe))
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
        appetitive_state = self._ensure_finite("appetitive_state", float(appetitive_state))

        cfg = self.config
        rpe_val = self.last_rpe if rpe is None else float(rpe)
        rpe_val = self._ensure_finite("rpe", rpe_val)

        # phasic
        self.phasic_level = float(max(0.0, rpe_val) * cfg["burst_factor"])

        # tonic (EMA)
        decay = float(cfg["decay_rate"])
        self.tonic_level = float((1.0 - decay) * self.tonic_level + decay * (appetitive_state + self.phasic_level))
        self._ensure_finite("tonic_level", self.tonic_level)

        # tonic/phasic balance
        denom = max(1e-6, abs(self.phasic_level))
        ratio = self.tonic_level / denom
        # clamp to reasonable range to avoid telemetry blow ups
        ratio = max(0.0, min(ratio, 100.0))
        self.tonic_to_phasic_ratio = float(ratio)

        # bounded logistic
        x = float(cfg["k"]) * (self.tonic_level - float(cfg["theta"]))
        x = max(min(x, 60.0), -60.0)
        sig = 1.0 / (1.0 + math.exp(-x))
        self.dopamine_level = float(min(1.0, max(0.0, sig)))

        self._log("dopamine_tonic_level", self.tonic_level)
        self._log("dopamine_phasic_level", self.phasic_level)
        self._log("dopamine_level", self.dopamine_level)
        self._log("dopamine_tonic_to_phasic_ratio", self.tonic_to_phasic_ratio)
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
        da = self._ensure_finite("dopamine_signal", da)
        dg = float(self.config["delta_gain"] if delta_gain is None else delta_gain)
        b = float(self.config["baseline"] if baseline is None else baseline)
        original_value = self._ensure_finite("original_value", float(original_value))
        result = float(original_value * (1.0 + dg * (da - b)))
        return result

    def compute_temperature(self, dopamine_signal: Optional[float] = None) -> float:
        da = self.dopamine_level if dopamine_signal is None else float(dopamine_signal)
        da = self._ensure_finite("dopamine_signal", da)
        base = float(self.config["base_temperature"])
        tmin = float(self.config["min_temperature"])
        k_t = float(self.config["temp_k"])

        temp = base * math.exp(-k_t * da)

        # підвищення температури при негативному RPE (швидкий перехід до exploration)
        neg_gain = float(self.config.get("neg_rpe_temp_gain", 0.5))
        max_mul = float(self.config.get("max_temp_multiplier", 3.0))
        if self.last_rpe < 0:
            temp *= min(max_mul, 1.0 + neg_gain * max(0.0, -self.last_rpe))

        temp = max(tmin, temp)
        if not math.isfinite(temp):
            raise ValueError("Temperature calculation produced a non-finite value")
        self._log("dopamine_temperature", temp)
        return float(temp)

    def check_invigoration(self, dopamine_signal: Optional[float] = None) -> bool:
        da = self.dopamine_level if dopamine_signal is None else float(dopamine_signal)
        da = min(1.0, max(0.0, da))
        return bool(da > float(self.config["invigoration_threshold"]))

    def check_suppress(self, dopamine_signal: Optional[float] = None) -> bool:
        da = self.dopamine_level if dopamine_signal is None else float(dopamine_signal)
        da = min(1.0, max(0.0, da))
        return bool(da < float(self.config["no_go_threshold"]))

    # ---------- meta-adapt ----------

    def meta_adapt(self, performance_metrics: Mapping[str, float]) -> None:
        drawdown = self._ensure_finite("drawdown", float(performance_metrics["drawdown"]))
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
            if key == "learning_rate_v":
                new_value = min(max(new_value, 1e-6), 1.0)
            elif key == "delta_gain":
                new_value = min(max(new_value, 0.0), 1.0)
            elif key == "base_temperature":
                new_value = max(float(cfg["min_temperature"]), new_value)
            cfg[key] = new_value
            self._log(f"dopamine_meta_{key}", new_value - old_value)

        self._log("dopamine_meta_state", {"good": 1.0, "bad": -1.0}.get(state, 0.0))
        if state != "neutral" and self._meta_cooldown > 0:
            self._meta_cooldown_counter = self._meta_cooldown

        self.save_config_to_yaml()

    # ---------- service ----------

    def update_metrics(self) -> None:
        self._metric_interval = max(1, int(self.config.get("metric_interval", self._metric_interval)))
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
            state: dict(rules) for state, rules in serialisable_cfg["meta_adapt_rules"].items()
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
            "tonic_to_phasic_ratio": float(self.tonic_to_phasic_ratio),
            "discount_gamma": float(self.config["discount_gamma"]),
            "learning_rate_v": float(self.config["learning_rate_v"]),
            "delta_gain": float(self.config["delta_gain"]),
            "base_temperature": float(self.config["base_temperature"]),
            "novelty_mode": str(self.config.get("novelty_mode", "external")),
            "c_absrpe": float(self.config.get("c_absrpe", 0.1)),
            "version": str(self.config.get("version", "unknown")),
        }

    def reset_state(self) -> None:
        self.tonic_level = 0.0
        self.phasic_level = 0.0
        self.dopamine_level = 0.0
        self.value_estimate = 0.0
        self.last_rpe = 0.0
        self.tonic_to_phasic_ratio = 0.0

    def dump_state(self) -> Mapping[str, float]:
        return {
            "tonic_level": self.tonic_level,
            "phasic_level": self.phasic_level,
            "dopamine_level": self.dopamine_level,
            "value_estimate": self.value_estimate,
            "last_rpe": self.last_rpe,
            "tonic_to_phasic_ratio": self.tonic_to_phasic_ratio,
        }

    def load_state(self, state: Mapping[str, float]) -> None:
        required_keys = {"tonic_level", "phasic_level", "dopamine_level", "value_estimate", "last_rpe"}
        missing = required_keys - set(state.keys())
        if missing:
            raise ValueError(f"State missing keys: {sorted(missing)}")
        self.tonic_level = self._ensure_finite("tonic_level", float(state["tonic_level"]))
        self.phasic_level = self._ensure_finite("phasic_level", float(state["phasic_level"]))
        self.dopamine_level = min(
            1.0,
            max(0.0, self._ensure_finite("dopamine_level", float(state["dopamine_level"]))),
        )
        self.value_estimate = self._ensure_finite("value_estimate", float(state["value_estimate"]))
        self.last_rpe = self._ensure_finite("last_rpe", float(state["last_rpe"]))
        if "tonic_to_phasic_ratio" in state:
            ratio = float(state["tonic_to_phasic_ratio"])
            self.tonic_to_phasic_ratio = max(0.0, min(float(ratio), 100.0))
        else:
            denom = max(1e-6, abs(self.phasic_level))
            self.tonic_to_phasic_ratio = float(max(0.0, min(self.tonic_level / denom, 100.0)))
