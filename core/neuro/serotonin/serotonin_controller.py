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
    cooldown_threshold: float = Field(
        ..., ge=0.0, le=1.0, description="Serotonin signal threshold for veto"
    )
    desens_threshold_ticks: int = Field(
        ..., ge=0, description="Ticks above threshold before desensitisation"
    )
    desens_rate: float = Field(
        ..., ge=0.0, le=1.0, description="Recovery rate when below threshold"
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
        self._tick_hours = float(cfg.get("tick_hours", 1.0))
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

    def compute_serotonin_signal(self, aversive_state: float) -> float:
        if aversive_state < 0:
            raise ValueError("aversive_state must be non-negative")

        with self._lock:
            cfg = self.config
            kappa = cfg["phase_kappa"]
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
                    self.sensitivity = max(
                        0.1,
                        self.sensitivity * math.exp(-cfg["desens_gain"] * sig),
                    )
            else:
                self.desens_counter = 0
                self.sensitivity = min(
                    1.0, self.sensitivity + cfg["desens_rate"] * 0.5
                )
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
            if serotonin_signal is None:
                serotonin_signal = self.serotonin_level
            veto = (
                serotonin_signal > self.config["cooldown_threshold"]
                or self.phasic_level > self.config["phasic_veto"]
                or self.gate_level > self.config["gate_veto"]
            )
            if self._tacl_guard and veto:
                payload = {
                    "serotonin_signal": float(serotonin_signal),
                    "phasic_level": float(self.phasic_level),
                    "gate_level": float(self.gate_level),
                }
                accepted = self._tacl_guard("serotonin_cooldown", payload)
                self._log("serotonin_cooldown_guard", float(accepted))
                if not accepted:
                    return False
            return veto

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
                "alpha": float(self.config["alpha"]),
                "beta": float(self.config["beta"]),
                "gamma": float(self.config["gamma"]),
                "decay_rate": float(self.config["decay_rate"]),
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
