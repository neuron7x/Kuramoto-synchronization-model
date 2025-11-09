from __future__ import annotations

import json
import logging
import math
import os
from pathlib import Path
from threading import RLock
from time import time
from typing import Callable, Mapping, Optional

import fcntl
import numpy as np
import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError


class SerotoninConfig(BaseModel):
    """Pydantic model describing the serotonin controller configuration."""

    alpha: float = Field(..., ge=0.0, description="Weight for market volatility")
    beta: float = Field(..., ge=0.0, description="Weight for free energy term")
    gamma: float = Field(..., ge=0.0, description="Weight for cumulative losses")
    delta_rho: float = Field(
        ..., description="Weight for rho-loss complement", ge=0.0, le=5.0
    )
    stress_gain: float = Field(
        1.0, ge=0.0, description="Scaling applied to stress input in tonic drive"
    )
    drawdown_gain: float = Field(
        1.0, ge=0.0, description="Scaling applied to positive drawdown magnitude"
    )
    novelty_gain: float = Field(
        1.0, ge=0.0, description="Scaling applied to novelty input for phasic drive"
    )
    k: float = Field(..., gt=0.0, description="Logistic steepness parameter")
    theta: float = Field(
        ..., description="Logistic mid-point for tonic level", ge=-5.0, le=5.0
    )
    delta: float = Field(..., ge=0.0, le=5.0, description="Inhibition multiplier")
    za_bias: float = Field(
        ..., ge=-1.0, le=1.0, description="Zero-action bias applied post inhibition"
    )
    decay_rate: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="Tonic decay rate per decision step"
    )
    phasic_decay: float = Field(
        0.35, ge=0.0, le=1.0, description="Decay rate for phasic component blending"
    )
    hold_threshold: float = Field(
        0.7, ge=0.0, le=1.0, description="Signal threshold that activates HOLD"
    )
    release_threshold: float = Field(
        0.55,
        ge=0.0,
        le=1.0,
        description="Signal threshold below which HOLD can be released",
    )
    desens_threshold_ticks: int = Field(
        ..., ge=0, description="Ticks above threshold before desensitisation"
    )
    desens_rate: float = Field(
        ..., ge=0.0, le=1.0, description="Recovery rate when below threshold"
    )
    sensitivity_floor: float = Field(
        0.1,
        ge=0.0,
        le=1.0,
        description="Lower bound for serotonin sensitivity during desensitisation",
    )
    target_dd: float = Field(..., description="Target drawdown for meta-adapt")
    target_sharpe: float = Field(
        ..., description="Target Sharpe for meta-adapt", gt=0.0
    )
    beta_temper: float = Field(
        ..., ge=0.0, le=1.0, description="Gradient tempering coefficient"
    )
    phase_threshold: float = Field(
        ..., ge=0.0, description="Threshold for triggering phasic bursts"
    )
    phase_kappa: float = Field(
        ..., gt=0.0, description="Smoothing factor for phasic gate sigmoid"
    )
    burst_factor: float = Field(
        ..., ge=0.0, description="Scaling factor for phasic component"
    )
    mod_t_max: float = Field(
        ..., gt=0.0, description="Time constant for modulation saturation"
    )
    mod_t_half: float = Field(
        ..., gt=0.0, description="Half-life for modulation decay"
    )
    mod_k: float = Field(
        ..., description="Modulation gain", ge=-5.0, le=5.0
    )
    max_desens_counter: int = Field(
        ..., ge=1, description="Maximum desensitisation counter"
    )
    desens_gain: float = Field(
        ..., gt=0.0, description="Gain applied during desensitisation"
    )
    gate_veto: float = Field(
        0.9,
        ge=0.0,
        le=1.0,
        description="Gate level above which cooldown veto triggers",
    )
    phasic_veto: float = Field(
        1.0,
        ge=0.0,
        description="Phasic level above which cooldown veto triggers",
    )
    temperature_floor_min: float = Field(
        0.05,
        ge=0.0,
        le=1.0,
        description="Lower bound for the serotonin-governed temperature floor",
    )
    temperature_floor_max: float = Field(
        0.6,
        ge=0.0,
        le=1.0,
        description="Upper bound for the serotonin-governed temperature floor",
    )
    cooldown_base_ticks: int = Field(
        12,
        ge=0,
        description="Baseline number of ticks to hold the cooldown veto",
    )
    cooldown_growth: float = Field(
        40.0,
        ge=0.0,
        description="Additional cooldown ticks per unit level above hold threshold",
    )
    cooldown_max_ticks: int = Field(
        240,
        ge=1,
        description="Maximum cooldown ticks regardless of stress level",
    )
    hold_guard_ticks: int = Field(
        90,
        ge=0,
        description="Number of consecutive hold ticks before guard approval is required",
    )
    stress_desens_threshold: float = Field(
        0.6,
        ge=0.0,
        description="Minimum tonic drive considered prolonged stress for desensitisation",
    )
    tau_5ht_ms: Optional[float] = Field(
        None, gt=0.0, description="Tonic decay time constant in milliseconds"
    )
    step_ms: Optional[float] = Field(
        None, gt=0.0, description="Decision step duration in milliseconds"
    )
    tick_hours: float = Field(
        1.0, gt=0.0, description="Wall-clock hours represented by a controller tick"
    )

    model_config = ConfigDict(extra="forbid")


def _generate_config_table(schema: dict) -> str:
    """Render the configuration schema into a Markdown table."""

    headers = ["Key", "Type", "Constraints", "Description"]
    rows = ["| " + " | ".join(headers) + " |", "| --- | --- | --- | --- |"]
    properties = schema.get("properties", {})
    required = set(schema.get("required", []))
    for key, meta in properties.items():
        typ = meta.get("type", "float")
        constraints_parts = []
        for bound in ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum"):
            if bound in meta:
                constraints_parts.append(f"{bound}={meta[bound]}")
        if key in required:
            constraints_parts.append("required")
        description = meta.get("description", "")
        rows.append(
            f"| {key} | {typ} | {'; '.join(constraints_parts) or '—'} | {description} |"
        )
    return "\n".join(rows)


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
        resolved_path = self._resolve_config_path(config_path)
        self.config_path = str(resolved_path)
        with open(resolved_path, "r", encoding="utf-8") as f:
            raw_cfg = yaml.safe_load(f)
        try:
            config_model = SerotoninConfig.model_validate(raw_cfg)
        except ValidationError as exc:
            raise ValueError(f"Invalid serotonin configuration: {exc}") from exc
        self._config_model = config_model
        self.config = config_model.model_dump()
        self._config_schema = SerotoninConfig.model_json_schema()
        self._validate_and_derive()
        self.tonic_level: float = 0.0
        self.sensitivity: float = 1.0
        self.desens_counter: int = 0
        self.serotonin_level: float = 0.0
        self.phasic_level: float = 0.0
        self.gate_level: float = 0.0
        self.temperature_floor: float = float(self.config["temperature_floor_min"])
        self._cooldown_ticks_remaining: int = 0
        self._hold_active: bool = False
        self._hold_ticks: int = 0
        self.hold_signal: bool = False
        self._base_signal: float = 0.0
        self._logger: Callable[[str, float], None] = logger or (
            lambda name, value: logging.getLogger(__name__).info("%s: %f", name, value)
        )
        self._tacl_guard: Optional[Callable[[str, Mapping[str, float]], bool]] = None
        self._lock = RLock()
        self._file_lock_path = Path(self.config_path).with_suffix(".lock")

    @staticmethod
    def noop_logger(name: str, value: float) -> None:
        """No-op logger compatible with the controller interface."""

        return None

    @staticmethod
    def prometheus_logger(collector: Callable[[str, float, Mapping[str, str]], None]) -> Callable[[str, float], None]:
        """Wrap a collector callable for Prometheus-style metrics."""

        def _log(name: str, value: float) -> None:
            collector(name, float(value), {"controller_version": "v2.3.1"})

        return _log

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
        tau_ms = cfg.get("tau_5ht_ms")
        step_ms = cfg.get("step_ms")
        logger = logging.getLogger(__name__)
        if tau_ms and step_ms:
            cfg["decay_rate"] = 1.0 - math.exp(-step_ms / tau_ms)
            logger.info(
                "SerotoninController τ-calibration: tau_ms=%.3f, step_ms=%.3f, decay_rate=%.6f",
                tau_ms,
                step_ms,
                cfg["decay_rate"],
            )
        if cfg.get("decay_rate") is None:
            raise KeyError("decay_rate must be provided when tau_5ht_ms/step_ms are absent")
        floor_min = cfg["temperature_floor_min"]
        floor_max = cfg["temperature_floor_max"]
        if floor_min > floor_max:
            raise ValueError(
                "temperature_floor_min must be less than or equal to temperature_floor_max"
            )
        if cfg["release_threshold"] > cfg["hold_threshold"]:
            raise ValueError("release_threshold must be less than or equal to hold_threshold")
        if cfg["cooldown_max_ticks"] < cfg["cooldown_base_ticks"]:
            raise ValueError("cooldown_max_ticks must be >= cooldown_base_ticks")
        self._tick_hours = float(cfg.get("tick_hours", 1.0))
        if step_ms:
            self._tick_seconds = float(step_ms) / 1000.0
        else:
            self._tick_seconds = float(self._tick_hours) * 3600.0
        if self._tick_seconds <= 0.0:
            raise ValueError("tick duration must be positive")
        logger.debug(
            "SerotoninController tick_hours=%.3f implies logistic saturation bounds (0,1)",
            self._tick_hours,
        )

    def set_tacl_guard(self, guard_fn: Callable[[str, Mapping[str, float]], bool]) -> None:
        """Inject a TACL guard to prevent free-energy regressions."""

        self._tacl_guard = guard_fn

    @staticmethod
    def _resolve_config_path(config_path: str) -> Path:
        """Resolve the configuration path with backwards compatibility support."""

        candidate = Path(config_path)
        if candidate.is_file():
            return candidate
        env_dir = os.getenv("TRADEPULSE_CONFIG_DIR")
        if env_dir:
            for name in (candidate.name, "serotonin.yaml"):
                env_candidate = Path(env_dir) / name
                if env_candidate.is_file():
                    logging.getLogger(__name__).warning(
                        "Using serotonin config from TRADEPULSE_CONFIG_DIR=%s", env_dir
                    )
                    return env_candidate
        legacy_candidate = Path("config") / candidate.name
        if legacy_candidate.is_file():
            logging.getLogger(__name__).warning(
                "Using deprecated serotonin config path %s; migrate to configs/", legacy_candidate
            )
            return legacy_candidate
        raise FileNotFoundError(f"Serotonin configuration not found at {config_path}")

    def config_schema(self) -> dict:
        """Return the JSON schema describing the serotonin configuration."""

        return self._config_schema

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
        rho_loss = max(-1.0, min(1.0, rho_loss))
        release = (
            alpha * market_vol
            + beta * free_energy
            + gamma * cum_losses
            + delta_rho * (1.0 - rho_loss)
        )
        return float(max(0.0, release))

    def _apply_dynamics(self, tonic_drive: float, phasic_drive: float) -> float:
        cfg = self.config
        tonic_drive = max(0.0, float(tonic_drive))
        phasic_drive = max(0.0, float(phasic_drive))
        gate = 1.0 / (
            1.0
            + math.exp(
                -(tonic_drive - cfg["phase_threshold"]) / max(cfg["phase_kappa"], 1e-6)
            )
        )
        self.gate_level = float(gate)
        phasic_target = phasic_drive + cfg["burst_factor"] * gate * (
            tonic_drive / (1.0 + tonic_drive)
        )
        phasic_decay = cfg["phasic_decay"]
        self.phasic_level = (1.0 - phasic_decay) * self.phasic_level + phasic_decay * phasic_target
        decay = cfg["decay_rate"]
        tonic_target = tonic_drive + self.phasic_level
        self.tonic_level = (1.0 - decay) * self.tonic_level + decay * tonic_target
        k = cfg["k"]
        theta = cfg["theta"]
        x = k * (self.tonic_level - theta)
        x = max(min(x, 60.0), -60.0)
        self._base_signal = 1.0 / (1.0 + math.exp(-x))
        return self._base_signal

    def _update_temperature_floor(self) -> None:
        cfg = self.config
        floor_min = cfg["temperature_floor_min"]
        floor_max = cfg["temperature_floor_max"]
        self.temperature_floor = float(
            floor_min + (floor_max - floor_min) * self.serotonin_level
        )

    def _finalise_step(self, raw_level: float, tonic_drive: float) -> tuple[bool, bool]:
        cfg = self.config
        level = float(np.clip(raw_level * self.sensitivity, 0.0, 1.0))
        hold_threshold = cfg["hold_threshold"]
        release_threshold = cfg["release_threshold"]
        prolonged_stress = tonic_drive >= cfg["stress_desens_threshold"]

        if level >= hold_threshold:
            self.desens_counter = min(
                self.desens_counter + 1, int(cfg["max_desens_counter"])
            )
            if prolonged_stress and self.desens_counter >= cfg["desens_threshold_ticks"]:
                self.sensitivity = max(
                    cfg["sensitivity_floor"],
                    self.sensitivity * math.exp(-cfg["desens_gain"] * level),
                )
            if not self._hold_active:
                self._hold_ticks = 1
            else:
                self._hold_ticks += 1
            self._hold_active = True
            cooldown = cfg["cooldown_base_ticks"] + math.ceil(
                max(0.0, level - hold_threshold) * cfg["cooldown_growth"]
            )
            cooldown = int(min(cfg["cooldown_max_ticks"], max(cooldown, 0)))
            self._cooldown_ticks_remaining = max(self._cooldown_ticks_remaining, cooldown)
        else:
            if self.desens_counter > 0:
                self.desens_counter -= 1
            self.sensitivity = min(1.0, self.sensitivity + cfg["desens_rate"])
            if self._cooldown_ticks_remaining > 0:
                self._cooldown_ticks_remaining -= 1
            veto_active = self._cooldown_ticks_remaining > 0
            if self._hold_active or veto_active:
                self._hold_ticks += 1
            else:
                self._hold_ticks = 0
            if self._hold_active and not veto_active and level <= release_threshold:
                release_allowed = True
                if self._tacl_guard and self._hold_ticks >= cfg["hold_guard_ticks"]:
                    payload = {
                        "level": float(level),
                        "hold_ticks": float(self._hold_ticks),
                        "cooldown_ticks": float(self._cooldown_ticks_remaining),
                    }
                    release_allowed = self._tacl_guard("serotonin_hold_release", payload)
                    self._log("tacl.5ht.guard_release", float(bool(release_allowed)))
                if release_allowed:
                    self._hold_active = False
                    self._hold_ticks = 0
                else:
                    self._cooldown_ticks_remaining = max(self._cooldown_ticks_remaining, 1)

        self.serotonin_level = float(np.clip(raw_level * self.sensitivity, 0.0, 1.0))
        self._update_temperature_floor()
        veto = self._cooldown_ticks_remaining > 0
        hold = self._hold_active or veto
        self.hold_signal = hold
        return hold, veto

    def step(self, stress: float, drawdown: float, novelty: float) -> tuple[bool, bool, float, float]:
        """Advance the serotonin controller by one decision tick.

        Args:
            stress: Normalised stress drive (≥0).
            drawdown: Portfolio drawdown (negative values indicate losses).
            novelty: Novelty/surprise drive (≥0).

        Returns:
            A tuple ``(hold, veto, cooldown_seconds, level)`` describing the
            HOLD signal, cooldown veto, cooldown timer in seconds and the
            serotonin level after desensitisation.
        """

        stress = max(0.0, float(stress))
        novelty = max(0.0, float(novelty))
        drawdown = float(drawdown)
        loss_mag = max(0.0, -drawdown)

        with self._lock:
            tonic_drive = self.config["stress_gain"] * stress + self.config["drawdown_gain"] * loss_mag
            phasic_drive = self.config["novelty_gain"] * novelty
            raw = self._apply_dynamics(tonic_drive, phasic_drive)
            hold, veto = self._finalise_step(raw, tonic_drive)
            cooldown_seconds = float(self._cooldown_ticks_remaining * self._tick_seconds)
            self._log("tacl.5ht.level", self.serotonin_level)
            self._log("tacl.5ht.hold", 1.0 if hold else 0.0)
            self._log("tacl.5ht.cooldown", cooldown_seconds)
            return hold, veto, cooldown_seconds, self.serotonin_level

    def compute_serotonin_signal(self, aversive_state: float) -> float:
        if aversive_state < 0:
            raise ValueError("aversive_state must be non-negative")

        with self._lock:
            raw = self._apply_dynamics(float(aversive_state), 0.0)
            hold, _ = self._finalise_step(raw, float(aversive_state))
            if hold:
                self._log("tacl.5ht.level", self.serotonin_level)
                self._log("tacl.5ht.hold", 1.0)
                self._log(
                    "tacl.5ht.cooldown", float(self._cooldown_ticks_remaining * self._tick_seconds)
                )
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

        with self._lock:
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

        with self._lock:
            if serotonin_signal is not None:
                # Allow external probes to override the current level for compatibility.
                self.serotonin_level = float(np.clip(serotonin_signal, 0.0, 1.0))
            veto = self._cooldown_ticks_remaining > 0
            hold = self._hold_active or veto
            if self._tacl_guard and hold:
                payload = {
                    "serotonin_signal": float(self.serotonin_level),
                    "phasic_level": float(self.phasic_level),
                    "gate_level": float(self.gate_level),
                    "cooldown_ticks": float(self._cooldown_ticks_remaining),
                }
                accepted = self._tacl_guard("serotonin_cooldown", payload)
                self._log("serotonin_cooldown_guard", float(accepted))
                if not accepted:
                    return False
            return hold

    def apply_internal_shift(
        self,
        exploitation_gradient: float,
        serotonin_signal: Optional[float] = None,
        beta_temper: Optional[float] = None,
    ) -> float:
        """Temper the exploitation gradient based on the serotonin signal."""

        if exploitation_gradient < 0:
            raise ValueError("exploitation_gradient must be non-negative")

        with self._lock:
            if serotonin_signal is None:
                serotonin_signal = self.serotonin_level
            if beta_temper is None:
                beta_temper = self.config["beta_temper"]
            return float(exploitation_gradient * (1.0 - beta_temper * serotonin_signal))

    def update_metrics(self) -> None:
        """Push serotonin telemetry to the logger backend."""

        with self._lock:
            tag = '{controller_version="v2.3.1"}'
            self._log(f"serotonin_level{tag}", self.serotonin_level)
            self._log(f"serotonin_tonic_level{tag}", self.tonic_level)
            self._log(f"serotonin_sensitivity{tag}", self.sensitivity)
            self._log(f"serotonin_phasic_level{tag}", self.phasic_level)
            self._log(f"serotonin_gate_level{tag}", self.gate_level)
            self._log(f"serotonin_decay_rate{tag}", self.config["decay_rate"])
            self._log(f"serotonin_temperature_floor{tag}", self.temperature_floor)
            cooldown_seconds = float(self._cooldown_ticks_remaining * self._tick_seconds)
            self._log("tacl.5ht.level", self.serotonin_level)
            self._log("tacl.5ht.hold", 1.0 if self.hold_signal else 0.0)
            self._log("tacl.5ht.cooldown", cooldown_seconds)

    def meta_adapt(self, performance_metrics: Mapping[str, float]) -> None:
        """Adapt release weights based on drawdown and Sharpe observations."""

        with self._lock:
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
            decision = 1.0
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
                accepted = self._tacl_guard("serotonin_meta_adapt", proposal)
                decision = 1.0 if accepted else 0.0
                if not accepted:
                    cfg["alpha"] = old_alpha
                    cfg["beta"] = old_beta
                    cfg["gamma"] = old_gamma
                    self._log("serotonin_meta_adapt_guard", 0.0)
                    return
            self._log("serotonin_meta_adapt_guard", decision)
            self._log("serotonin_alpha_drift", cfg["alpha"] - old_alpha)
            self._log("serotonin_beta_drift", cfg["beta"] - old_beta)
            self._log("serotonin_gamma_drift", cfg["gamma"] - old_gamma)
            self.save_config_to_yaml()

    def save_config_to_yaml(self, path: Optional[str] = None) -> None:
        """Persist the current configuration to disk."""

        with self._lock:
            target = path or self.config_path
            tmp_target = f"{target}.tmp"
            with open(tmp_target, "w", encoding="utf-8") as f:
                yaml.safe_dump(self.config, f)
                f.flush()
                os.fsync(f.fileno())
            try:
                self._with_file_lock(lambda: os.replace(tmp_target, target))
            except Exception:
                if os.path.exists(tmp_target):
                    os.remove(tmp_target)
                raise
            audit_dir = Path(target).parent / "audit"
            audit_dir.mkdir(parents=True, exist_ok=True)
            timestamp = time()
            audit_target = audit_dir / f"serotonin_{int(timestamp)}.yaml"
            with open(audit_target, "w", encoding="utf-8") as audit_file:
                yaml.safe_dump(self.config, audit_file)
                audit_file.flush()
                os.fsync(audit_file.fileno())
            if os.path.exists(tmp_target):
                os.remove(tmp_target)

    def to_dict(self) -> dict:
        """Expose serialisable controller state for audits and telemetry."""

        with self._lock:
            return {
                "tonic_level": float(self.tonic_level),
                "sensitivity": float(self.sensitivity),
                "desens_counter": int(self.desens_counter),
                "serotonin_level": float(self.serotonin_level),
                "phasic_level": float(self.phasic_level),
                "gate_level": float(self.gate_level),
                "temperature_floor": float(self.temperature_floor),
                "alpha": float(self.config["alpha"]),
                "beta": float(self.config["beta"]),
                "gamma": float(self.config["gamma"]),
                "decay_rate": float(self.config["decay_rate"]),
                "hold_active": bool(self._hold_active),
                "cooldown_ticks_remaining": int(self._cooldown_ticks_remaining),
                "hold_ticks": int(self._hold_ticks),
                "hold_signal": bool(self.hold_signal),
            }

    def _with_file_lock(self, action: Callable[[], None]) -> None:
        """Execute ``action`` while holding an inter-process file lock."""

        lock_path = self._file_lock_path
        with open(lock_path, "w", encoding="utf-8") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                action()
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


if __name__ == "__main__":  # pragma: no cover - utility for documentation
    schema = SerotoninConfig.model_json_schema()
    print(json.dumps(schema, indent=2))
    print()
    print(_generate_config_table(schema))
