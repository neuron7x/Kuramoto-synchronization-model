"""Serotonin-inspired risk inhibition controller for trading systems.

This module implements a sophisticated risk management system inspired by the
serotonergic system in neuroscience. Serotonin acts as an inhibitory signal that
suppresses risky trading actions during adverse conditions (drawdowns, volatility).

The controller combines multiple components:
    - Tonic level: Baseline inhibition computed from market state and losses
    - Phasic bursts: Rapid inhibition spikes triggered by threshold crossings
    - Desensitization: Adaptive reduction in response to sustained signals
    - Meta-adaptation: Long-term parameter adjustment toward target metrics
    - Temporal modulation: Time-dependent gating of inhibitory strength

Key Components:
    SerotoninConfig: Complete parameter specification with validation
    SerotoninState: Runtime state including tonic, phasic, and desensitization
    SerotoninController: Main controller with thread-safe state management
    gate_action: Apply inhibition to proposed trading actions

The system uses a logistic function to convert composite risk signals into
inhibition strength, with homeostatic mechanisms to prevent over-inhibition
and meta-learning to tune parameters toward target Sharpe and drawdown levels.

Features:
    - Thread-safe state updates with RLock
    - Persistent state snapshots to disk
    - File-based locking for multi-process safety
    - Meta-adaptation with gradient descent
    - Configurable phasic burst dynamics

Example:
    >>> config = SerotoninConfig.from_yaml("serotonin.yaml")
    >>> controller = SerotoninController(config)
    >>> proposed_action = 0.5  # 50% long
    >>> inhibited_action = controller.gate_action(
    ...     proposed_action, vol=0.03, free_energy=2.0, losses=-0.05, rho=0.2
    ... )
"""

from __future__ import annotations

import datetime as _dt
import fcntl
import json
import logging
import math
import os
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from time import perf_counter_ns, time
from typing import Any, Callable, Iterator, Literal, Mapping, Optional, Sequence

import numpy as np
import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from tradepulse.core.neuro.numeric_config import STABILITY_EPSILON

try:  # Allow loading as a standalone module in tests
    from tradepulse.core.neuro.serotonin.receptors import ParamDeltas, ReceptorBank, ReceptorContext
except ImportError:  # pragma: no cover - fallback for relative import
    from .receptors import ParamDeltas, ReceptorBank, ReceptorContext

__CANONICAL__ = True
DEFAULT_ACTIVE_PROFILE: Literal["v24", "legacy"] = "v24"


class _ConfigView(dict):
    """Dict-like config that also exposes attribute access."""

    def __getattr__(self, item: str):
        try:
            return self[item]
        except KeyError as exc:  # pragma: no cover - defensive
            raise AttributeError(item) from exc


class ReceptorConfig(BaseModel):
    """Optional receptor modulation settings."""

    enabled: bool = False
    enabled_list: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class SerotoninStepResult:
    """Hybrid tuple+mapping return type for SerotoninController.step().

    Temperature floor is exposed via mapping access only to preserve backward
    compatibility with legacy tuple unpacking (4-value tuples).
    """

    _KEY_INDEX = {"hold": 0, "veto": 1, "cooldown": 2, "level": 3}
    __slots__ = (
        "hold",
        "veto",
        "cooldown",
        "level",
        "temperature_floor",
        "desensitization",
    )

    def __init__(
        self,
        hold: bool,
        veto: bool,
        cooldown: float,
        level: float,
        temperature_floor: float,
        desensitization: float,
    ) -> None:
        self.hold = bool(hold)
        self.veto = bool(veto)
        self.cooldown = float(cooldown)
        self.level = float(level)
        self.temperature_floor = float(temperature_floor)
        self.desensitization = float(desensitization)

    def __iter__(self) -> Iterator[bool | float]:
        return iter(self._tuple_fields())

    def __getitem__(self, key: int | str) -> float | bool:
        fields = self._tuple_fields()
        if isinstance(key, int):
            if 0 <= key < len(fields):
                return fields[key]
            raise IndexError(f"Index {key} out of range, valid indices are 0-3")

        if key == "temperature_floor":
            return self.temperature_floor
        if key == "desensitization":
            return self.desensitization

        idx = self._KEY_INDEX.get(key)
        if idx is not None:
            return fields[idx]

        raise KeyError(
            f"Key {key!r} not found; valid keys are: hold, veto, cooldown, level, temperature_floor, desensitization"
        )

    def _tuple_fields(self) -> tuple[bool, bool, float, float]:
        return (self.hold, self.veto, self.cooldown, self.level)

    def to_dict(self) -> dict[str, float | bool]:
        return {
            "hold": self.hold,
            "veto": self.veto,
            "cooldown": self.cooldown,
            "level": self.level,
            "temperature_floor": self.temperature_floor,
            "desensitization": self.desensitization,
        }


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
        ..., gt=0.0, le=1.0, description="Serotonin signal threshold for veto"
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
    mod_t_half: float = Field(..., gt=0.0, description="Half-life for modulation decay")
    mod_k: float = Field(..., description="Modulation gain", ge=-5.0, le=5.0)
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
    receptors: ReceptorConfig = Field(
        default_factory=ReceptorConfig,
        description="Optional receptor-based parameter modulators (default disabled)",
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
    hysteresis_margin: float = Field(
        0.05,
        ge=0.01,
        le=0.15,
        description="Hysteresis margin for veto threshold transitions (v2.5.0)",
    )

    model_config = ConfigDict(extra="forbid")


SerotoninConfig.model_rebuild()


class SerotoninLegacyConfig(BaseModel):
    """Legacy serotonin configuration model (deprecated).

    This profile is maintained for backwards compatibility only.
    New deployments should use the v24 profile.
    """

    tonic_beta: float = Field(..., ge=0.0, le=1.0, description="Tonic beta coefficient")
    phasic_beta: float = Field(..., ge=0.0, le=1.0, description="Phasic beta coefficient")
    stress_gain: float = Field(..., ge=0.0, description="Stress gain multiplier")
    drawdown_gain: float = Field(..., ge=0.0, description="Drawdown gain multiplier")
    novelty_gain: float = Field(..., ge=0.0, description="Novelty gain multiplier")
    stress_threshold: float = Field(..., ge=0.0, le=1.0, description="Stress threshold")
    release_threshold: float = Field(..., ge=0.0, le=1.0, description="Release threshold")
    hysteresis: float = Field(..., ge=0.0, le=1.0, description="Hysteresis margin")
    cooldown_ticks: int = Field(..., ge=0, description="Cooldown ticks")
    chronic_window: int = Field(..., ge=1, description="Chronic window size")
    desensitization_rate: float = Field(..., ge=0.0, le=1.0, description="Desensitization rate")
    desensitization_decay: float = Field(..., ge=0.0, le=1.0, description="Desensitization decay")
    max_desensitization: float = Field(..., ge=0.0, le=1.0, description="Max desensitization")
    floor_min: float = Field(..., ge=0.0, le=1.0, description="Floor minimum")
    floor_max: float = Field(..., ge=0.0, le=1.0, description="Floor maximum")
    floor_gain: float = Field(..., ge=0.0, description="Floor gain")
    cooldown_extension: int = Field(..., ge=0, description="Cooldown extension ticks")

    model_config = ConfigDict(extra="forbid")


class SerotoninConfigEnvelope(BaseModel):
    """Strict root-level serotonin configuration wrapper.

    Supports multi-profile configurations:
    - v24: Current production profile (recommended)
    - legacy: Deprecated profile for backwards compatibility

    The active_profile field selects which profile to use at runtime.
    """

    active_profile: Literal["v24", "legacy"] = DEFAULT_ACTIVE_PROFILE
    serotonin_v24: Optional[SerotoninConfig] = None
    serotonin_legacy: Optional[SerotoninLegacyConfig] = None

    model_config = ConfigDict(extra="forbid")

    def get_active_config(self) -> tuple[SerotoninConfig, Literal["v24", "legacy"]]:
        """Return the active configuration based on active_profile.

        Returns:
            Tuple of (config, profile_name)

        Raises:
            ValueError: If the active profile's configuration is missing.
        """
        if self.active_profile == "v24":
            if self.serotonin_v24 is None:
                raise ValueError(
                    "active_profile is 'v24' but serotonin_v24 section is missing"
                )
            return self.serotonin_v24, "v24"
        elif self.active_profile == "legacy":
            if self.serotonin_legacy is None:
                raise ValueError(
                    "active_profile is 'legacy' but serotonin_legacy section is missing"
                )
            # Log deprecation warning only once per class (module-level dedup)
            if not getattr(SerotoninConfigEnvelope, "_legacy_warned", False):
                logging.getLogger(__name__).warning(
                    "Using deprecated 'legacy' serotonin profile. "
                    "Migrate to 'v24' profile for improved functionality."
                )
                SerotoninConfigEnvelope._legacy_warned = True
            # Map legacy fields to v24 equivalents
            # Compute max_desens_counter with bounds to prevent overflow
            raw_max_desens = (
                self.serotonin_legacy.max_desensitization
                / max(self.serotonin_legacy.desensitization_rate, 0.01)
            )
            bounded_max_desens = min(max(int(raw_max_desens), 1), 10000)
            hysteresis_margin = float(self.serotonin_legacy.hysteresis)
            if hysteresis_margin < 0.01 or hysteresis_margin > 0.15:
                clamped_margin = min(max(hysteresis_margin, 0.01), 0.15)
                logging.getLogger(__name__).warning(
                    "Clamping legacy hysteresis margin %.4f to %.4f for v24 compatibility",
                    hysteresis_margin,
                    clamped_margin,
                )
                hysteresis_margin = clamped_margin
            v24_config = SerotoninConfig(
                alpha=self.serotonin_legacy.stress_gain * 0.5,
                beta=self.serotonin_legacy.tonic_beta,
                gamma=self.serotonin_legacy.drawdown_gain * 0.33,
                delta_rho=self.serotonin_legacy.novelty_gain * 0.3,
                k=1.5,
                theta=0.0,
                delta=0.5,
                za_bias=0.0,
                decay_rate=self.serotonin_legacy.desensitization_decay,
                cooldown_threshold=self.serotonin_legacy.stress_threshold,
                desens_threshold_ticks=self.serotonin_legacy.cooldown_ticks,
                desens_rate=self.serotonin_legacy.desensitization_rate,
                target_dd=0.15,
                target_sharpe=1.5,
                beta_temper=0.5,
                phase_threshold=self.serotonin_legacy.release_threshold,
                phase_kappa=2.0,
                burst_factor=self.serotonin_legacy.phasic_beta,
                mod_t_max=10.0,
                mod_t_half=5.0,
                mod_k=0.5,
                max_desens_counter=bounded_max_desens,
                desens_gain=0.8,
                gate_veto=0.9,
                phasic_veto=1.0,
                temperature_floor_min=self.serotonin_legacy.floor_min,
                temperature_floor_max=self.serotonin_legacy.floor_max,
                hysteresis_margin=hysteresis_margin,
            )
            return v24_config, "legacy"
        else:
            raise ValueError(f"Unknown active_profile: {self.active_profile}")


REASON_CODES_WHITELIST: tuple[str, ...] = (
    "STRESS_HIGH",
    "DRAWDOWN_SPIKE",
    "UNCERTAINTY_HIGH",
    "COOLDOWN_ACTIVE",
    "RECOVERY_INSUFFICIENT",
    "INVARIANT_BROKEN",
    "INVALID_INPUT",
    "NUMERIC_UNSTABLE",
    "LEVEL_OOB",
    "BUDGET_OOB",
    "STRESS_MONOTONICITY",
    "RISK_BUDGET_CLAMPED",
)
STRESS_BUDGET_MULTIPLIER = 0.7
BUDGET_TOLERANCE = STABILITY_EPSILON


@dataclass(slots=True)
class ControllerOutput:
    mode: str
    risk_budget: float
    action_gate: str
    reason_codes: tuple[str, ...]
    metrics_snapshot: Mapping[str, float | int | str]


class SafetyMonitor:
    """Lightweight runtime safety monitor for serotonin controller."""

    __slots__ = (
        "_min_budget",
        "_max_budget",
        "_last_stress",
        "_last_budget",
    )

    def __init__(self, min_budget: float, max_budget: float = 1.0) -> None:
        self._min_budget = float(min_budget)
        self._max_budget = float(max_budget)
        self._last_stress: Optional[float] = None
        self._last_budget: Optional[float] = None

    def validate_inputs(self, observation: Mapping[str, float]) -> tuple[bool, str | None]:
        """Return (ok, reason) after validating inputs."""
        required = ("stress", "drawdown", "novelty")
        for key in required:
            if key not in observation:
                return False, "INVALID_INPUT"
            value = observation[key]
            if isinstance(value, bool):
                value = float(value)
            if value is None or isinstance(value, complex):
                return False, "INVALID_INPUT"
            try:
                as_float = float(value)
            except (TypeError, ValueError):
                return False, "INVALID_INPUT"
            if not math.isfinite(as_float):
                return False, "INVALID_INPUT"
            if key in ("stress", "novelty") and as_float < 0:
                return False, "INVALID_INPUT"
        return True, None

    def check_invariants(
        self,
        serotonin_level: float,
        risk_budget: float,
        hold: bool,
        stress: float,
        *,
        clamped_budget: bool = False,
    ) -> tuple[bool, Sequence[str], "OrderedDict[str, bool]"]:
        reasons: list[str] = []
        checks: "OrderedDict[str, bool]" = OrderedDict()
        finite_ok = math.isfinite(serotonin_level) and math.isfinite(risk_budget) and math.isfinite(stress)
        checks["finite_inputs"] = finite_ok
        in_bounds = finite_ok and (0.0 <= serotonin_level <= 1.0)
        checks["serotonin_in_bounds"] = in_bounds
        budget_bounds = finite_ok and (self._min_budget <= risk_budget <= self._max_budget)
        checks["risk_budget_in_bounds"] = budget_bounds
        monotonic_ok = True
        if self._last_stress is not None and self._last_budget is not None:
            monotonic_ok = not (
                stress > self._last_stress and risk_budget > self._last_budget + BUDGET_TOLERANCE
            )
        checks["stress_monotonic"] = monotonic_ok
        checks["risk_budget_clamped"] = bool(clamped_budget)
        checks["hold_state"] = bool(hold)

        if not finite_ok:
            reasons.append("INVALID_INPUT")
        if not in_bounds:
            reasons.append("LEVEL_OOB")
        if not budget_bounds:
            reasons.append("BUDGET_OOB")
        if not monotonic_ok:
            reasons.append("STRESS_MONOTONICITY")
        if hold:
            reasons.append("COOLDOWN_ACTIVE")

        inv_ok = finite_ok and in_bounds and budget_bounds and monotonic_ok
        if inv_ok:
            self._last_stress = stress
            self._last_budget = risk_budget
        return inv_ok, reasons, checks

    def reset(self) -> None:
        self._last_stress = None
        self._last_budget = None

    def state(self) -> Mapping[str, float | None]:
        return {
            "last_stress": self._last_stress,
            "last_budget": self._last_budget,
            "min_budget": self._min_budget,
            "max_budget": self._max_budget,
        }


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


def _load_single_yaml_document(path: Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        docs = list(yaml.safe_load_all(f))
    if len(docs) == 0:
        return {}
    if len(docs) > 1:
        raise ValueError(
            f"Multi-document configs are not supported for serotonin: found {len(docs)} documents in {path}"
        )
    doc = docs[0] or {}
    if not isinstance(doc, dict):
        raise ValueError("Serotonin configuration must be a mapping at the root")
    return doc


class SerotoninController:
    """SerotoninController v2.4.0 tonic–phasic stabiliser with TACL guardrails.

    Enhanced version with improved action/rest potential dynamics:
    - Adaptive gate sensitivity based on tonic level
    - Non-linear phasic burst dynamics with saturation
    - Improved tonic-phasic separation with adaptive decay
    - Enhanced desensitization with exponential recovery curves
    - Hysteresis-based veto logic for smoother state transitions
    - Non-linear aversive state estimation with biological transforms
    - Progressive inhibition curves for realistic neuromodulation
    - Cubic temperature floor interpolation for smoother adaptation
    """

    @staticmethod
    def _load_config(
        path: Path,
    ) -> tuple[SerotoninConfigEnvelope, SerotoninConfig, Literal["v24", "legacy"]]:
        """Load and validate serotonin configuration from YAML.

        Supports multi-profile configs with active_profile selector.
        """
        raw_cfg = _load_single_yaml_document(path)
        legacy_field_keys = set(SerotoninLegacyConfig.model_fields.keys())
        if "active_profile" not in raw_cfg:
            raw_keys = set(raw_cfg.keys())
            if "serotonin_v24" in raw_cfg or "serotonin_legacy" in raw_cfg:
                default_profile = (
                    DEFAULT_ACTIVE_PROFILE if "serotonin_v24" in raw_cfg else "legacy"
                )
                logging.getLogger(__name__).warning(
                    "No active_profile provided; defaulting to '%s' profile", default_profile
                )
                raw_cfg = {"active_profile": default_profile, **raw_cfg}
            elif raw_keys & legacy_field_keys:
                logging.getLogger(__name__).warning(
                    "Detected legacy serotonin keys without active_profile; "
                    "defaulting to legacy profile. Set active_profile=legacy to silence."
                )
                raw_cfg = {"active_profile": "legacy", "serotonin_legacy": raw_cfg}
            else:
                logging.getLogger(__name__).warning(
                    "No active_profile provided; defaulting to %s profile.",
                    DEFAULT_ACTIVE_PROFILE,
                )
                raw_cfg = {
                    "active_profile": DEFAULT_ACTIVE_PROFILE,
                    "serotonin_v24": raw_cfg,
                }

        allowed_root = {"active_profile", "serotonin_v24", "serotonin_legacy"}
        unknown_root = sorted(set(raw_cfg.keys()) - allowed_root)
        if unknown_root:
            raise ValueError(
                f"Unknown root keys in serotonin config: {unknown_root}. "
                f"Allowed: {sorted(allowed_root)}"
            )
        try:
            envelope = SerotoninConfigEnvelope.model_validate(raw_cfg)
        except ValidationError as exc:
            raise ValueError(f"Invalid serotonin root configuration: {exc}") from exc
        config_model, active_profile = envelope.get_active_config()
        return envelope, config_model, active_profile

    def __init__(
        self,
        config_path: str = "configs/serotonin.yaml",
        logger: Optional[Callable[[str, float], None]] = None,
        *,
        min_risk_budget: float = 0.05,
        enable_performance_tracking: bool | None = None,
    ):
        """Initialise the controller with a YAML configuration.

        Args:
            config_path: Path to the serotonin configuration file.
            logger: Optional metric logger callable. Falls back to
                :func:`logging.info` if omitted.
        """
        resolved_path = self._resolve_config_path(config_path)
        self.config_path = str(resolved_path)
        envelope, config_model, active_profile = self._load_config(resolved_path)
        self._config_envelope = envelope
        self._config_model = config_model
        self.config = _ConfigView(config_model.model_dump())
        self.config["floor_min"] = self.config.get(
            "temperature_floor_min", self.config.get("floor_min")
        )
        self.config["floor_max"] = self.config.get(
            "temperature_floor_max", self.config.get("floor_max")
        )
        self._config_schema = SerotoninConfig.model_json_schema()
        self._validate_and_derive()
        self._active_profile = active_profile
        self.tonic_level: float = 0.0
        self.sensitivity: float = 1.0
        self.desens_counter: int = 0
        self.serotonin_level: float = 0.0
        self.phasic_level: float = 0.0
        self.gate_level: float = 0.0
        self.temperature_floor: float = float(self.config["temperature_floor_min"])
        self._logger: Callable[[str, float], None] = logger or (
            lambda name, value: logging.getLogger(__name__).info("%s: %f", name, value)
        )
        self._tacl_guard: Optional[Callable[[str, Mapping[str, float]], bool]] = None
        self._lock = RLock()
        self._file_lock_path = Path(self.config_path).with_suffix(".lock")
        self._cooldown_start_time: Optional[float] = None
        self._hold_state: bool = False
        self._hold: bool = False
        self._cooldown: float = 0.0

        # Performance tracking
        self._step_count: int = 0
        self._total_cooldown_time: float = 0.0
        self._veto_count: int = 0
        self._last_step_time: Optional[float] = None
        self._perf_tracking_enabled = bool(
            True if enable_performance_tracking is None else enable_performance_tracking
        )
        self._min_risk_budget = float(min_risk_budget)
        self._max_risk_budget = 1.0
        self._safety_monitor = SafetyMonitor(self._min_risk_budget, self._max_risk_budget)
        self._trace_events: list[str] = []
        self._last_event: OrderedDict[str, object] | None = None
        self._last_decision: ControllerOutput | None = None
        self._time_provider = lambda: _dt.datetime.now(_dt.timezone.utc)
        self._receptors_cfg = dict(self.config.get("receptors", {"enabled": False, "enabled_list": []}))
        self._receptor_bank: Optional[ReceptorBank] = None
        if self._receptors_cfg.get("enabled"):
            self._receptor_bank = ReceptorBank(self._receptors_cfg.get("enabled_list"))
        self._receptor_prev_stress: Optional[float] = None
        self._last_receptor_trace: Optional[Mapping[str, Mapping[str, float | bool]]] = None
        self._last_receptor_budget_cap: Optional[float] = None

    @staticmethod
    def noop_logger(name: str, value: float) -> None:
        """No-op logger compatible with the controller interface."""

        return None

    @staticmethod
    def prometheus_logger(
        collector: Callable[[str, float, Mapping[str, str]], None],
    ) -> Callable[[str, float], None]:
        """Wrap a collector callable for Prometheus-style metrics."""

        def _log(name: str, value: float) -> None:
            collector(name, float(value), {"controller_version": "v2.4.0"})

        return _log

    def _log(self, name: str, value: float) -> None:
        """Record a telemetry datapoint via the configured logger."""

        try:
            self._logger(name, float(value))
        except Exception as exc:
            # Logging must not interfere with control flow.
            logging.getLogger(__name__).debug(
                "SerotoninController logger failed for %s: %s", name, exc
            )

    def _validate_and_derive(self) -> None:
        """Validate configuration keys and derive dependent quantities."""

        cfg = self.config
        tau_ms = cfg.get("tau_5ht_ms")
        step_ms = cfg.get("step_ms")
        logger = logging.getLogger(__name__)
        if tau_ms and step_ms:
            if tau_ms <= 0 or step_ms <= 0:
                raise ValueError("tau_5ht_ms and step_ms must be positive")
            ratio = -step_ms / tau_ms
            cfg["decay_rate"] = -math.expm1(ratio)
            logger.info(
                "SerotoninController τ-calibration: tau_ms=%.3f, step_ms=%.3f, decay_rate=%.6f",
                tau_ms,
                step_ms,
                cfg["decay_rate"],
            )
        if cfg.get("decay_rate") is None:
            raise KeyError(
                "decay_rate must be provided when tau_5ht_ms/step_ms are absent"
            )
        if not (0.0 < cfg["decay_rate"] <= 1.0):
            raise ValueError("decay_rate must be within (0, 1]")
        if cfg["cooldown_threshold"] <= 0.0:
            raise ValueError("cooldown_threshold must be greater than 0")
        floor_min = cfg["temperature_floor_min"]
        floor_max = cfg["temperature_floor_max"]
        if floor_min > floor_max:
            raise ValueError(
                "temperature_floor_min must be less than or equal to temperature_floor_max"
            )
        self._tick_hours = float(cfg.get("tick_hours", 1.0))
        logger.debug(
            "SerotoninController tick_hours=%.3f implies logistic saturation bounds (0,1)",
            self._tick_hours,
        )

    def _build_receptor_context(
        self,
        stress: float,
        drawdown: float,
        novelty: float,
        vol: float,
        free_energy: float,
        dt: Optional[float],
    ) -> ReceptorContext:
        prev = self._receptor_prev_stress
        shock_norm = 0.0
        if prev is not None:
            shock_norm = abs(stress - prev) / max(0.1, prev + 0.5)
        self._receptor_prev_stress = stress
        volatility_norm = float(min(1.0, math.tanh(max(0.0, vol))))
        drawdown_norm = float(min(1.0, abs(drawdown)))
        novelty_norm = float(min(1.0, math.tanh(max(0.0, novelty))))
        impulse_dt = (
            float(dt) if dt is not None else (time() - self._last_step_time) if self._last_step_time else 1.0
        )
        impulse_pressure = 1.0 / max(impulse_dt, 1e-3)
        impulse_pressure_norm = float(min(1.0, math.tanh(impulse_pressure)))
        regime_entropy_norm = float(min(1.0, math.tanh(abs(novelty) + abs(vol - drawdown))))
        return ReceptorContext(
            volatility_norm=volatility_norm,
            drawdown_norm=drawdown_norm,
            novelty_norm=novelty_norm,
            shock_norm=float(min(1.0, shock_norm)),
            impulse_pressure_norm=impulse_pressure_norm,
            regime_entropy_norm=regime_entropy_norm,
            circadian_phase=None,
            temperature_floor=float(self.temperature_floor),
        )

    def _apply_param_deltas(
        self, base: Mapping[str, float], deltas: ParamDeltas
    ) -> Mapping[str, float | bool]:
        floor_min = float(self.config["temperature_floor_min"])
        floor_max = float(self.config["temperature_floor_max"])
        temp_floor = float(
            max(floor_min, min(floor_max, base["temperature_floor"] + deltas.temperature_floor_delta))
        )
        hysteresis_margin = float(
            max(0.01, min(0.2, base["hysteresis_margin"] + deltas.hold_hysteresis_delta))
        )
        veto_bias = max(-0.2, min(0.5, deltas.veto_bias))
        cooldown_threshold = float(
            max(0.05, base["cooldown_threshold"] * (1.0 - 0.3 * max(veto_bias, 0.0)))
        )
        gate_veto = float(max(0.0, min(1.2, base["gate_veto"] * (1.0 - 0.2 * max(veto_bias, 0.0)))))
        phasic_veto = float(
            max(0.0, min(1.2, base["phasic_veto"] * (1.0 - 0.2 * max(veto_bias, 0.0))))
        )
        cooldown_s = float(max(0.0, base["cooldown_s"] + deltas.cooldown_s))
        risk_cap = float(base["risk_budget_cap"])
        # Spec: pos_mult_cap is decrease-only; ignore positive deltas to avoid risk inflation.
        if deltas.pos_mult_cap_delta < 0:
            risk_cap = float(max(self._min_risk_budget, risk_cap + deltas.pos_mult_cap_delta))
        serotonin_level = float(
            max(0.0, min(1.0, base["serotonin_level"] * (1.0 + deltas.tonic_weight_delta)))
        )
        phasic_level = float(max(0.0, base["phasic_level"] * (1.0 + deltas.phasic_weight_delta)))
        return {
            "temperature_floor": temp_floor,
            "hysteresis_margin": hysteresis_margin,
            "cooldown_threshold": cooldown_threshold,
            "gate_veto": gate_veto,
            "phasic_veto": phasic_veto,
            "cooldown_s": cooldown_s,
            "risk_budget_cap": risk_cap,
            "serotonin_level": serotonin_level,
            "phasic_level": phasic_level,
            "force_veto": bool(deltas.force_veto),
        }

    def set_tacl_guard(
        self, guard_fn: Callable[[str, Mapping[str, float]], bool]
    ) -> None:
        """Inject a TACL guard to prevent free-energy regressions."""

        self._tacl_guard = guard_fn

    def step(
        self,
        stress: float,
        drawdown: float,
        novelty: float,
        market_vol: Optional[float] = None,
        free_energy: Optional[float] = None,
        cum_losses: Optional[float] = None,
        rho_loss: Optional[float] = None,
        dt: Optional[float] = None,
    ) -> SerotoninStepResult:
        """Execute one serotonin control step and return decision signals.

        This is the primary API for risk/fatigue control integration. It consolidates
        the aversive state estimation, serotonin signal computation, and cooldown
        decision into a single call.

        Args:
            stress: Current stress level (0.0 to unbounded, typically 0-3).
            drawdown: Current drawdown (negative value, e.g., -0.05 for 5% drawdown).
            novelty: Novelty/uncertainty measure (0.0 to unbounded, typically 0-2).
            market_vol: Optional market volatility override. If None, uses stress.
            free_energy: Optional free energy override. If None, uses novelty.
            cum_losses: Optional cumulative losses override. If None, uses abs(drawdown).
            rho_loss: Optional rho-loss complement. If None, defaults to 0.0.

        Returns:
            A SerotoninStepResult that behaves like both a tuple and mapping:
            - Tuple iteration/unpacking returns (hold, veto, cooldown, level)
            - Mapping keys expose hold, veto, cooldown, level, temperature_floor
              (temperature_floor is mapping-only to keep tuple arity stable)

        Raises:
            ValueError: If stress, drawdown magnitude, or novelty are negative.

        Example:
            >>> controller = SerotoninController()
            >>> hold, veto, cooldown_s, level = controller.step(
            ...     stress=1.2, drawdown=-0.03, novelty=0.8
            ... )
            >>> if hold:
            ...     print(f"HOLD triggered: level={level:.3f}, cooldown={cooldown_s:.1f}s")
        """
        raw_drawdown = drawdown
        if stress < 0:
            raise ValueError("stress must be non-negative")
        if self._active_profile == "v24" and raw_drawdown > 0:
            if not getattr(self, "_positive_drawdown_warned", False):
                logging.getLogger(__name__).warning(
                    "drawdown should be negative or zero (e.g., -0.05 for 5%% loss); "
                    "received %.4f, coercing to negative",
                    raw_drawdown,
                )
                self._positive_drawdown_warned = True
        drawdown = -abs(raw_drawdown)
        if novelty < 0:
            raise ValueError("novelty must be non-negative")

        with self._lock:
            # Map high-level inputs to aversive state estimation
            vol = market_vol if market_vol is not None else stress
            fe = free_energy if free_energy is not None else novelty
            losses = cum_losses if cum_losses is not None else abs(drawdown)
            rho = rho_loss if rho_loss is not None else 0.0

            # Compute aversive state and serotonin signal
            aversive = self.estimate_aversive_state(vol, fe, losses, rho)
            level = self.compute_serotonin_signal(aversive)

            base_params = {
                "temperature_floor": float(self.temperature_floor),
                "hysteresis_margin": float(self.config.get("hysteresis_margin", 0.05)),
                "cooldown_threshold": float(self.config["cooldown_threshold"]),
                "gate_veto": float(self.config["gate_veto"]),
                "phasic_veto": float(self.config["phasic_veto"]),
                "cooldown_s": 0.0,
                "risk_budget_cap": float(self._max_risk_budget),
                "serotonin_level": float(level),
                "phasic_level": float(self.phasic_level),
            }
            receptors_enabled = bool(self._receptor_bank and self._receptors_cfg.get("enabled"))
            activations = {}
            params = base_params
            if receptors_enabled and self._receptor_bank:
                ctx = self._build_receptor_context(stress, drawdown, novelty, vol, fe, dt)
                activations, deltas = self._receptor_bank.run(ctx)
                params = self._apply_param_deltas(base_params, deltas)
                self._last_receptor_trace = {"activations": activations, "deltas": deltas.to_dict()}
            else:
                self._last_receptor_trace = None
            serotonin_level_eff = float(params.get("serotonin_level", level))
            phasic_level_eff = float(params.get("phasic_level", self.phasic_level))
            hysteresis_margin = float(params.get("hysteresis_margin", base_params["hysteresis_margin"]))
            cooldown_threshold = float(params.get("cooldown_threshold", self.config["cooldown_threshold"]))
            gate_veto_th = float(params.get("gate_veto", self.config["gate_veto"]))
            phasic_veto_th = float(params.get("phasic_veto", self.config["phasic_veto"]))
            cooldown_bias = float(params.get("cooldown_s", 0.0))
            temperature_floor_out = float(params.get("temperature_floor", self.temperature_floor))
            force_veto = bool(params.get("force_veto", False))
            budget_cap_override = float(params.get("risk_budget_cap", self._max_risk_budget))
            overrides = None
            if receptors_enabled:
                overrides = {
                    "hysteresis_margin": hysteresis_margin,
                    "cooldown_threshold": cooldown_threshold,
                    "gate_veto": gate_veto_th,
                    "phasic_veto": phasic_veto_th,
                    "phasic_level": phasic_level_eff,
                    "gate_level": self.gate_level,
                }
                self._last_receptor_budget_cap = budget_cap_override
            else:
                self._last_receptor_budget_cap = None

            # Check cooldown and track hold state
            veto = self.check_cooldown(serotonin_level_eff, overrides=overrides)
            hold = veto or force_veto
            if force_veto:
                veto = True
            if stress >= 1.0 or abs(drawdown) >= 0.5:
                veto = True
                hold = True

            # Track cooldown timer
            current_time = time()
            if hold and not self._hold_state:
                # Entering cooldown
                self._cooldown_start_time = current_time
                self._hold_state = True
                self._hold = True
                self._cooldown = max(0.0, cooldown_bias)
            elif not hold and self._hold_state:
                # Exiting cooldown
                self._hold_state = False
                self._cooldown_start_time = None
                self._cooldown = max(float(self.config.get("desens_threshold_ticks", 0)), cooldown_bias)
            else:
                self._hold = bool(self._hold_state)
                if hold:
                    self._cooldown = max(self._cooldown, cooldown_bias)

            # Calculate cooldown duration
            cooldown_s = 0.0
            if self._hold_state and self._cooldown_start_time is not None:
                cooldown_s = current_time - self._cooldown_start_time
            elif not self._hold_state and self._cooldown > 0:
                cooldown_s = self._cooldown
            if not self._hold_state and self._cooldown > 0:
                step_dt = float(dt) if dt is not None else 1.0
                self._cooldown = max(0.0, self._cooldown - step_dt)
            self._hold = bool(self._hold_state)
            cooldown_s = max(cooldown_s, cooldown_bias)

            # Track performance metrics
            self._step_count += 1
            if hold:
                self._veto_count += 1
                if cooldown_s > 0:
                    self._total_cooldown_time += current_time - (
                        self._last_step_time or current_time
                    )
            self._last_step_time = current_time

            # Emit TACL telemetry
            self.temperature_floor = temperature_floor_out
            self._log("tacl.5ht.level", serotonin_level_eff)
            self._log("tacl.5ht.hold", float(hold))
            self._log("tacl.5ht.cooldown", cooldown_s)

            desensitization = max(0.0, 1.0 - self.sensitivity)
            return SerotoninStepResult(
                hold=hold,
                veto=veto,
                cooldown=cooldown_s,
                level=serotonin_level_eff,
                temperature_floor=self.temperature_floor,
                desensitization=desensitization,
            )

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
                "Using deprecated serotonin config path %s; migrate to configs/",
                legacy_candidate,
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
        """Estimate aversive state from market conditions.

        Combines multiple stress signals with configurable weights:
        - market_vol (alpha): External market volatility/uncertainty
        - free_energy (beta): Internal model uncertainty/surprise
        - cum_losses (gamma): Accumulated losses (pain signal)
        - rho_loss (delta_rho): Portfolio correlation losses

        Enhanced with non-linear transformations for biological plausibility.
        """
        for name, value in (
            ("market_vol", market_vol),
            ("free_energy", free_energy),
            ("cum_losses", cum_losses),
            ("rho_loss", rho_loss),
        ):
            try:
                as_float = float(value)
            except (TypeError, ValueError):
                raise ValueError(f"{name} must be a finite number") from None
            if not math.isfinite(as_float):
                raise ValueError(f"{name} must be finite")
        if market_vol < 0 or free_energy < 0 or cum_losses < 0:
            raise ValueError(
                "market_vol, free_energy and cum_losses must be non-negative"
            )

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

        # Clamp rho_loss to valid range
        rho_loss = max(-1.0, min(1.0, rho_loss))

        # Apply non-linear transformations for better sensitivity
        # Square root for diminishing returns at high values (Weber-Fechner law)
        vol_contribution = alpha * math.sqrt(market_vol) if market_vol > 0 else 0.0

        # Free energy uses linear scaling (uncertainty should be directly proportional)
        fe_contribution = beta * free_energy

        # Cumulative losses use accelerating function (pain intensifies)
        # Use quadratic for losses to emphasize large drawdowns
        loss_contribution = gamma * (cum_losses + 0.5 * cum_losses**2)

        # Rho-loss complement (decorrelation benefit)
        rho_contribution = delta_rho * (1.0 - rho_loss)

        # Weighted sum with saturation
        release = (
            vol_contribution + fe_contribution + loss_contribution + rho_contribution
        )

        # Apply soft saturation to prevent unbounded growth
        # Using tanh-based saturation for smooth asymptotic behavior
        saturated = 3.0 * math.tanh(release / 3.0)

        return float(max(0.0, saturated))

    def compute_serotonin_signal(self, aversive_state: float) -> float:
        if not math.isfinite(aversive_state):
            raise ValueError("aversive_state must be finite")
        if aversive_state < 0:
            raise ValueError("aversive_state must be non-negative")

        with self._lock:
            cfg = self.config

            # Adaptive gate sensitivity based on current tonic level
            # Higher tonic → lower kappa → sharper gate response (better action onset)
            kappa_base = cfg["phase_kappa"]
            tonic_adaptation = 1.0 - 0.3 * min(self.tonic_level / 2.0, 1.0)
            kappa = kappa_base * tonic_adaptation

            # Improved phasic gate with steeper sigmoid for sharper action potentials
            gate_raw = (aversive_state - cfg["phase_threshold"]) / kappa
            gate_raw = max(min(gate_raw, 20.0), -20.0)  # Numerical stability
            gate = 1.0 / (1.0 + math.exp(-gate_raw))
            self.gate_level = float(gate)

            # Enhanced phasic component with saturation for realistic burst dynamics
            # Using Michaelis-Menten-like saturation for biological plausibility
            phasic_saturation = aversive_state / (1.0 + aversive_state)
            phasic_burst = cfg["burst_factor"] * gate * phasic_saturation
            # Add phasic decay to prevent accumulation
            self.phasic_level = float(0.7 * self.phasic_level + 0.3 * phasic_burst)

            # Improved tonic dynamics with separate slow integration
            # Tonic should integrate slowly, phasic provides fast transients
            decay = cfg["decay_rate"]
            # Adaptive decay: faster when gate is low (rest), slower during action
            effective_decay = decay * (
                1.0 - 0.3 * gate
            )  # Reduced from 0.4 to 0.3 for better integration
            # Balance between direct aversive input and phasic contribution
            # Use 0.5 instead of 0.3 to maintain adequate tonic build-up
            tonic_input = (
                float(aversive_state) + 0.5 * phasic_burst
            )  # Use burst not level for proper scaling
            self.tonic_level = (
                1.0 - effective_decay
            ) * self.tonic_level + effective_decay * tonic_input

            # Enhanced sigmoid transformation with better numerical stability
            k = cfg["k"]
            theta = cfg["theta"]
            x = k * (self.tonic_level - theta)
            x = max(min(x, 60.0), -60.0)
            sig = 1.0 / (1.0 + math.exp(-x))

            # Improved desensitization with exponential recovery curve
            max_counter = int(cfg["max_desens_counter"])
            if self.tonic_level > cfg["cooldown_threshold"]:
                self.desens_counter = min(self.desens_counter + 1, max_counter)
                if self.desens_counter > cfg["desens_threshold_ticks"]:
                    # Non-linear desensitization: accelerates with prolonged activation
                    desens_factor = 1.0 + 0.5 * (self.desens_counter / max_counter)
                    self.sensitivity = max(
                        0.1,
                        self.sensitivity
                        * math.exp(-cfg["desens_gain"] * sig * desens_factor),
                    )
            else:
                # Exponential recovery with temperature-dependent rate
                # Faster recovery when well below threshold
                recovery_boost = 1.0 + 0.5 * max(
                    0.0,
                    (cfg["cooldown_threshold"] - self.tonic_level)
                    / cfg["cooldown_threshold"],
                )
                recovery_rate = cfg["desens_rate"] * recovery_boost
                self.desens_counter = max(
                    0, self.desens_counter - 2
                )  # Gradual counter decay
                self.sensitivity = min(1.0, self.sensitivity + recovery_rate)

            # Final serotonin level with sensitivity modulation
            self.serotonin_level = float(sig * self.sensitivity)

            # Enhanced temperature floor with smoother interpolation
            floor_min = cfg["temperature_floor_min"]
            floor_max = cfg["temperature_floor_max"]
            # Use cubic interpolation for smoother transitions
            level_cubed = self.serotonin_level**3
            self.temperature_floor = float(
                floor_min + (floor_max - floor_min) * level_cubed
            )
            return self.serotonin_level

    def modulate_action_prob(
        self,
        original_prob: float,
        serotonin_signal: Optional[float] = None,
        za_bias: Optional[float] = None,
    ) -> float:
        """Apply serotonin-driven inhibition to an action probability.

        Uses non-linear inhibition curve for biological realism:
        - Low serotonin: minimal inhibition (exploration/action allowed)
        - Medium serotonin: progressive inhibition (caution)
        - High serotonin: strong inhibition (rest/avoidance)

        The inhibition follows a sigmoidal curve rather than linear suppression
        for more realistic neuromodulation dynamics.
        """

        if not 0.0 <= original_prob <= 1.0:
            raise ValueError("original_prob must be within [0, 1]")

        with self._lock:
            cfg = self.config
            if serotonin_signal is None:
                serotonin_signal = self.serotonin_level
            if za_bias is None:
                za_bias = cfg["za_bias"]

            # Non-linear inhibition with sigmoidal curve
            # This creates a smooth transition from action to rest
            delta = cfg["delta"]
            # Transform linear signal to sigmoidal inhibition
            inhibition_strength = (
                serotonin_signal**2
            )  # Quadratic for progressive effect
            inhibition_factor = 1.0 - inhibition_strength * delta

            # Apply inhibition
            inhibited = original_prob * max(0.0, inhibition_factor)

            # Apply zero-action bias (preference for no action under uncertainty)
            # Use sigmoid-like bias application for smooth transitions
            if za_bias < 0:
                # Negative bias reduces action probability
                bias_factor = 1.0 + za_bias * (1.0 - math.exp(-2.0 * serotonin_signal))
            else:
                # Positive bias increases action probability (rare, but supported)
                bias_factor = 1.0 + za_bias

            biased = inhibited * bias_factor

            return float(np.clip(biased, 0.0, 1.0))

    def check_cooldown(
        self, serotonin_signal: Optional[float] = None, overrides: Optional[Mapping[str, float]] = None
    ) -> bool:
        """Return ``True`` when the serotonin veto threshold is exceeded.

        Implements hysteresis-based veto logic with multi-level thresholds:
        - Primary: serotonin_level > cooldown_threshold
        - Phasic burst: phasic_level > phasic_veto (fast transient detection)
        - Gate override: gate_level > gate_veto (sustained high stress)

        Hysteresis prevents rapid oscillation at threshold boundaries by using
        slightly different thresholds for entering vs. exiting HOLD state.
        The hysteresis margin is now configurable via the config file (v2.5.0).
        """

        with self._lock:
            if serotonin_signal is None:
                serotonin_signal = self.serotonin_level

            cfg = self.config
            overrides = overrides or {}

            # Configurable hysteresis margin (v2.5.0)
            # Defaults to 5% of threshold for smooth transitions
            hysteresis_margin = float(overrides.get("hysteresis_margin", cfg.get("hysteresis_margin", 0.05)))

            # Calculate effective thresholds based on current hold state
            if self._hold_state:
                # When in HOLD, require signal to drop below threshold - margin to exit
                # This prevents premature exit from rest state
                serotonin_threshold = overrides.get("cooldown_threshold", cfg["cooldown_threshold"]) * (
                    1.0 - hysteresis_margin
                )
                phasic_threshold = overrides.get("phasic_veto", cfg["phasic_veto"]) * (1.0 - hysteresis_margin)
                gate_threshold = overrides.get("gate_veto", cfg["gate_veto"]) * (1.0 - hysteresis_margin)
            else:
                # When active, require signal to exceed threshold + margin to enter HOLD
                # This prevents premature entry to rest state
                serotonin_threshold = overrides.get("cooldown_threshold", cfg["cooldown_threshold"]) * (
                    1.0 + hysteresis_margin
                )
                phasic_threshold = overrides.get("phasic_veto", cfg["phasic_veto"]) * (1.0 + hysteresis_margin)
                gate_threshold = overrides.get("gate_veto", cfg["gate_veto"]) * (1.0 + hysteresis_margin)

            # Multi-level veto with weighted contribution
            # Serotonin level is primary, phasic and gate provide additional signals
            serotonin_veto = serotonin_signal > serotonin_threshold
            phasic_level = overrides.get("phasic_level", self.phasic_level)
            gate_level = overrides.get("gate_level", self.gate_level)
            phasic_veto = phasic_level > phasic_threshold
            gate_veto = gate_level > gate_threshold

            # Combined veto decision with logical OR (any threshold triggers veto)
            veto = serotonin_veto or phasic_veto or gate_veto

            # TACL guard validation for regulatory compliance
            if self._tacl_guard and veto:
                payload = {
                    "serotonin_signal": float(serotonin_signal),
                    "phasic_level": float(self.phasic_level),
                    "gate_level": float(self.gate_level),
                    "serotonin_veto": serotonin_veto,
                    "phasic_veto": phasic_veto,
                    "gate_veto": gate_veto,
                    "hold_state": self._hold_state,
                }
                accepted = self._tacl_guard("serotonin_cooldown", payload)
                self._log("serotonin_cooldown_guard", float(accepted))
                if not accepted:
                    return False

            return bool(veto)

    @property
    def hold(self) -> bool:
        """Compatibility property combining hold state and cooldown window."""

        return bool(self._hold_state or self._cooldown > 0)

    def apply_internal_shift(
        self,
        exploitation_gradient: float,
        serotonin_signal: Optional[float] = None,
        beta_temper: Optional[float] = None,
    ) -> float:
        """Temper the exploitation gradient based on the serotonin signal.

        High serotonin reduces exploitation (promotes exploration/caution).
        Uses non-linear tempering for smoother behavior:
        - Low serotonin: full exploitation allowed
        - Medium serotonin: gradual reduction in exploitation
        - High serotonin: strong suppression of exploitation

        This implements the explore-exploit balance modulated by stress/uncertainty.
        """

        if exploitation_gradient < 0:
            raise ValueError("exploitation_gradient must be non-negative")

        with self._lock:
            if serotonin_signal is None:
                serotonin_signal = self.serotonin_level
            if beta_temper is None:
                beta_temper = self.config["beta_temper"]

            # Non-linear tempering with cubic function for smooth transitions
            # This provides gentle tempering at low levels, stronger at high levels
            tempering_curve = serotonin_signal**1.5  # Power between 1 and 2 for balance
            tempering_factor = 1.0 - beta_temper * tempering_curve

            # Ensure non-negative result
            tempered_gradient = exploitation_gradient * max(0.0, tempering_factor)

            return float(tempered_gradient)

    def update_metrics(self) -> None:
        """Push serotonin telemetry to the logger backend."""

        with self._lock:
            tag = '{controller_version="v2.4.0"}'
            self._log(f"serotonin_level{tag}", self.serotonin_level)
            self._log(f"serotonin_tonic_level{tag}", self.tonic_level)
            self._log(f"serotonin_sensitivity{tag}", self.sensitivity)
            self._log(f"serotonin_phasic_level{tag}", self.phasic_level)
            self._log(f"serotonin_gate_level{tag}", self.gate_level)
            self._log(f"serotonin_decay_rate{tag}", self.config["decay_rate"])
            self._log(f"serotonin_temperature_floor{tag}", self.temperature_floor)
            # TACL telemetry
            self._log("tacl.5ht.level", self.serotonin_level)
            self._log("tacl.5ht.hold", float(self._hold_state))
            cooldown_s = 0.0
            if self._hold_state and self._cooldown_start_time is not None:
                cooldown_s = time() - self._cooldown_start_time
            self._log("tacl.5ht.cooldown", cooldown_s)

    # ------------------------------- Runtime safety + deterministic update API
    def _derive_risk_budget(
        self, serotonin_level: float, stress: float, max_budget: Optional[float] = None
    ) -> tuple[float, bool]:
        # Simple monotone transform: higher serotonin → lower budget
        budget_cap = float(max_budget) if max_budget is not None else self._max_risk_budget
        raw_budget = budget_cap * (1.0 - serotonin_level)
        # Mild additional suppression when stress is high to maintain monotonicity
        if stress > self.config["cooldown_threshold"]:
            raw_budget *= STRESS_BUDGET_MULTIPLIER
        clamped_budget = float(
            max(self._min_risk_budget, min(budget_cap, raw_budget))
        )
        return clamped_budget, bool(abs(clamped_budget - raw_budget) > BUDGET_TOLERANCE)

    def _fail_safe_output(self, reason: str) -> ControllerOutput:
        reasons = (reason,) if reason in REASON_CODES_WHITELIST else ("INVARIANT_BROKEN",)
        metrics = {
            "serotonin_level": float(self.serotonin_level),
            "tonic_level": float(self.tonic_level),
            "phasic_level": float(self.phasic_level),
            "gate_level": float(self.gate_level),
            "cooldown_s": 0.0,
            "update_latency_us": 0,
        }
        return ControllerOutput(
            mode="DEFENSIVE",
            risk_budget=self._min_risk_budget,
            action_gate="HOLD_OR_REDUCE_ONLY",
            reason_codes=reasons,
            metrics_snapshot=metrics,
        )

    def _record_event(
        self,
        output: ControllerOutput,
        observation: Mapping[str, float],
        serotonin_level: float,
        update_latency_us: int,
        invariants_checked: Mapping[str, bool] | None = None,
    ) -> None:
        now = self._time_provider()
        if now.tzinfo is not None:
            now = now.astimezone(_dt.timezone.utc).replace(tzinfo=None)
        invariants_checked = OrderedDict(invariants_checked or {})

        def _safe_float(key: str, default: float = 0.0) -> float:
            try:
                return float(observation.get(key, default))
            except Exception:
                return float(default)

        inputs_snapshot = OrderedDict(
            [
                ("stress", _safe_float("stress")),
                ("drawdown", _safe_float("drawdown")),
                ("novelty", _safe_float("novelty")),
                ("market_vol", _safe_float("market_vol")),
                ("free_energy", _safe_float("free_energy")),
                ("cum_losses", _safe_float("cum_losses")),
                ("rho_loss", _safe_float("rho_loss")),
            ]
        )
        outputs_snapshot = OrderedDict(
            [
                ("mode", output.mode),
                ("risk_budget", float(output.risk_budget)),
                ("gate", output.action_gate),
                ("serotonin_level", float(serotonin_level)),
            ]
        )
        receptor_snapshot = None
        if self._last_receptor_trace is not None:
            receptor_snapshot = {
                "activations": {k: float(v) for k, v in self._last_receptor_trace.get("activations", {}).items()},
                "deltas": self._last_receptor_trace.get("deltas", {}),
            }
        event = OrderedDict(
            [
                ("timestamp_utc", now.isoformat() + "Z"),
                ("schema_version", "1.0"),
                ("active_profile", self._active_profile),
                ("inputs", inputs_snapshot),
                ("outputs", outputs_snapshot),
                ("reason_codes", list(output.reason_codes)),
                ("invariants_checked", invariants_checked),
                ("update_latency_us", int(update_latency_us)),
            ]
        )
        if receptor_snapshot is not None:
            event["receptors"] = receptor_snapshot
        self._last_event = event
        self._trace_events.append(json.dumps(event, separators=(",", ":")))

    def update(self, observation: Mapping[str, float]) -> ControllerOutput:
        """Deterministic O(1) update with runtime safety monitoring."""

        start_ns = perf_counter_ns()
        ok, reason = self._safety_monitor.validate_inputs(observation)
        if not ok:
            output = self._fail_safe_output(reason or "INVALID_INPUT")
            self._last_decision = output
            self._record_event(output, observation, self.serotonin_level, 0, {})
            return output

        stress = float(observation["stress"])
        drawdown = float(observation["drawdown"])
        raw_drawdown = drawdown
        if self._active_profile == "v24" and raw_drawdown > 0:
            if not getattr(self, "_positive_drawdown_warned", False):
                logging.getLogger(__name__).warning(
                    "drawdown should be negative or zero (e.g., -0.05 for 5%% loss); "
                    "received %.4f, coercing to negative",
                    raw_drawdown,
                )
                self._positive_drawdown_warned = True
        drawdown = -abs(raw_drawdown)
        novelty = float(observation["novelty"])
        market_vol = float(observation.get("market_vol", stress))
        free_energy = float(observation.get("free_energy", novelty))
        cum_losses = float(observation.get("cum_losses", abs(drawdown)))
        rho_loss = float(observation.get("rho_loss", 0.0))

        try:
            hold, veto, cooldown_s, serotonin_level = self.step(
                stress=stress,
                drawdown=drawdown,
                novelty=novelty,
                market_vol=market_vol,
                free_energy=free_energy,
                cum_losses=cum_losses,
                rho_loss=rho_loss,
            )
        except (ValueError, OverflowError, ArithmeticError, TypeError):  # pragma: no cover - defensive fallback
            output = self._fail_safe_output("NUMERIC_UNSTABLE")
            self._last_decision = output
            self._record_event(output, observation, self.serotonin_level, 0, {})
            return output
        hold = bool(
            hold
            or stress >= self.config["cooldown_threshold"] * 1.5
            or drawdown < -0.15
        )
        veto = bool(veto or hold)

        update_latency_us = int((perf_counter_ns() - start_ns) / 1000)
        cap_override = self._last_receptor_budget_cap
        risk_budget, clamped_budget = self._derive_risk_budget(
            serotonin_level, stress, max_budget=cap_override
        )
        inv_ok, inv_reasons, invariant_flags = self._safety_monitor.check_invariants(
            serotonin_level, risk_budget, bool(hold), stress, clamped_budget=clamped_budget
        )
        reasons: list[str] = []
        if stress > self.config["cooldown_threshold"]:
            reasons.append("STRESS_HIGH")
        if drawdown < -0.05:
            reasons.append("DRAWDOWN_SPIKE")
        if novelty > 1.5:
            reasons.append("UNCERTAINTY_HIGH")
        if clamped_budget:
            reasons.append("RISK_BUDGET_CLAMPED")
        reasons.extend(inv_reasons)

        if not inv_ok:
            output = self._fail_safe_output(inv_reasons[0] if inv_reasons else "INVARIANT_BROKEN")
            self._record_event(
                output, observation, serotonin_level, update_latency_us, invariant_flags
            )
        else:
            action_gate = "HOLD_OR_REDUCE_ONLY" if hold or veto else "ALLOW"
            mode = "DEFENSIVE" if hold or veto else "NORMAL"
            metrics = {
                "serotonin_level": float(serotonin_level),
                "tonic_level": float(self.tonic_level),
                "phasic_level": float(self.phasic_level),
                "gate_level": float(self.gate_level),
                "cooldown_s": float(cooldown_s),
                "update_latency_us": update_latency_us,
            }
            filtered_reasons = tuple(rc for rc in reasons if rc in REASON_CODES_WHITELIST)
            output = ControllerOutput(
                mode=mode,
                risk_budget=risk_budget,
                action_gate=action_gate,
                reason_codes=filtered_reasons,
                metrics_snapshot=metrics,
            )
            self._record_event(
                output, observation, serotonin_level, update_latency_us, invariant_flags
            )

        self._last_decision = output
        return output

    def explain_last_decision(self) -> str:
        if self._last_event is None:
            return "No decisions have been made."
        event = self._last_event
        outputs = event.get("outputs", {})
        mode = outputs.get("mode", event.get("mode", "UNKNOWN"))
        risk_budget = float(outputs.get("risk_budget", event.get("risk_budget", 0.0)))
        gate = outputs.get("gate", event.get("gate", "UNKNOWN"))
        reasons = event.get("reason_codes", [])
        return (
            f"[{event['timestamp_utc']}] mode={mode} "
            f"risk_budget={risk_budget:.3f} "
            f"gate={gate} reasons={','.join(reasons)}"
        )

    def get_last_receptor_trace(self) -> Optional[Mapping[str, Mapping[str, float | bool]]]:
        """Expose the last receptor activation/delta trace for diagnostics."""

        return self._last_receptor_trace

    def get_state(self) -> Mapping[str, float | bool]:
        with self._lock:
            return {
                "tonic_level": float(self.tonic_level),
                "phasic_level": float(self.phasic_level),
                "serotonin_level": float(self.serotonin_level),
                "sensitivity": float(self.sensitivity),
                "gate_level": float(self.gate_level),
                "hold_state": bool(self._hold_state),
                "temperature_floor": float(self.temperature_floor),
            }

    def set_state(self, state: Mapping[str, float | bool]) -> None:
        with self._lock:
            for key in ("tonic_level", "phasic_level", "serotonin_level"):
                value = float(state[key])
                if not math.isfinite(value):
                    raise ValueError("state values must be finite")
            self.tonic_level = float(state["tonic_level"])
            self.phasic_level = float(state["phasic_level"])
            self.serotonin_level = float(state["serotonin_level"])
            self.sensitivity = float(state.get("sensitivity", self.sensitivity))
            self.gate_level = float(state.get("gate_level", self.gate_level))
            self._hold_state = bool(state.get("hold_state", self._hold_state))
            self.temperature_floor = float(
                state.get("temperature_floor", self.temperature_floor)
            )

    def export_trace_jsonl(self) -> str:
        """Return deterministic JSONL trace for audit."""
        return "\n".join(self._trace_events)

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
            config_payload = {
                key: self.config[key]
                for key in SerotoninConfig.model_fields
                if key in self.config
            }
            config_model = SerotoninConfig(**config_payload)
            if (
                self._active_profile == "legacy"
                and self._config_envelope.serotonin_legacy is not None
            ):
                serialized = {
                    "active_profile": "legacy",
                    "serotonin_legacy": self._config_envelope.serotonin_legacy.model_dump(),
                }
            else:
                serialized = {
                    "active_profile": "v24",
                    "serotonin_v24": config_model.model_dump(),
                }
            target = path or self.config_path
            tmp_target = f"{target}.tmp"
            with open(tmp_target, "w", encoding="utf-8") as f:
                yaml.safe_dump(serialized, f)
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
                yaml.safe_dump(serialized, audit_file)
                audit_file.flush()
                os.fsync(audit_file.fileno())
            if os.path.exists(tmp_target):
                os.remove(tmp_target)

    def to_dict(self) -> dict:
        """Expose serialisable controller state for audits and telemetry."""

        with self._lock:
            cooldown_s = 0.0
            if self._hold_state and self._cooldown_start_time is not None:
                cooldown_s = time() - self._cooldown_start_time
            return {
                "tonic_level": float(self.tonic_level),
                "sensitivity": float(self.sensitivity),
                "desens_counter": int(self.desens_counter),
                "serotonin_level": float(self.serotonin_level),
                "phasic_level": float(self.phasic_level),
                "gate_level": float(self.gate_level),
                "temperature_floor": float(self.temperature_floor),
                "cooldown": float(self._cooldown),
                "alpha": float(self.config["alpha"]),
                "beta": float(self.config["beta"]),
                "gamma": float(self.config["gamma"]),
                "decay_rate": float(self.config["decay_rate"]),
                "hold_state": bool(self._hold_state),
                "cooldown_s": float(cooldown_s),
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

    def save_state(self, path: str) -> None:
        """Save controller state to a JSON file for recovery or analysis.

        Args:
            path: Path to save the state file.

        Example:
            >>> controller.save_state("state/serotonin_checkpoint.json")
        """
        with self._lock:
            state = self.to_dict()
            state["_metadata"] = {
                "timestamp": time(),
                "config_path": self.config_path,
                "step_count": self._step_count,
                "total_cooldown_time": self._total_cooldown_time,
                "veto_count": self._veto_count,
            }
            target = Path(path)
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = f"{path}.tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2, sort_keys=True)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, path)
            logging.getLogger(__name__).info("Saved state to %s", path)

    def load_state(self, path: str) -> None:
        """Load controller state from a JSON file.

        Args:
            path: Path to the state file.

        Raises:
            FileNotFoundError: If the state file does not exist.
            ValueError: If the state file is invalid or incompatible.

        Example:
            >>> controller.load_state("state/serotonin_checkpoint.json")
        """
        with self._lock:
            target = Path(path)
            if not target.exists():
                raise FileNotFoundError(f"State file not found: {path}")

            with open(target, "r", encoding="utf-8") as f:
                state = json.load(f)

            # Restore core state
            self.tonic_level = float(state.get("tonic_level", 0.0))
            self.sensitivity = float(state.get("sensitivity", 1.0))
            self.desens_counter = int(state.get("desens_counter", 0))
            self.serotonin_level = float(state.get("serotonin_level", 0.0))
            self.phasic_level = float(state.get("phasic_level", 0.0))
            self.gate_level = float(state.get("gate_level", 0.0))
            self.temperature_floor = float(
                state.get("temperature_floor", self.config["temperature_floor_min"])
            )
            self._hold_state = bool(state.get("hold_state", False))
            self._cooldown = float(state.get("cooldown", 0.0))
            self._hold = bool(self._hold_state)

            # Restore metadata if available
            metadata = state.get("_metadata", {})
            self._step_count = int(metadata.get("step_count", 0))
            self._total_cooldown_time = float(metadata.get("total_cooldown_time", 0.0))
            self._veto_count = int(metadata.get("veto_count", 0))

            # Reset cooldown start time (don't persist absolute time)
            if self._hold_state:
                self._cooldown_start_time = time()
            else:
                self._cooldown_start_time = None

            logging.getLogger(__name__).info("Loaded state from %s", path)

    def reset(self) -> None:
        """Reset controller state to initial conditions.

        Useful for testing, recovery after errors, or starting a new trading session.
        Config parameters are preserved.

        Example:
            >>> controller.reset()
            >>> assert controller.serotonin_level == 0.0
        """
        with self._lock:
            self.tonic_level = 0.0
            self.sensitivity = 1.0
            self.desens_counter = 0
            self.serotonin_level = 0.0
            self.phasic_level = 0.0
            self.gate_level = 0.0
            self.temperature_floor = float(self.config["temperature_floor_min"])
            self._cooldown_start_time = None
            self._hold_state = False
            self._hold = False
            self._cooldown = 0.0
            self._step_count = 0
            self._total_cooldown_time = 0.0
            self._veto_count = 0
            self._last_step_time = None
            self._last_event = None
            self._last_decision = None
            self._trace_events.clear()
            self._safety_monitor.reset()
            self._receptor_prev_stress = None
            self._last_receptor_trace = None
            self._last_receptor_budget_cap = None
            if self._receptor_bank and self._receptors_cfg.get("enabled"):
                self._receptor_bank = ReceptorBank(self._receptors_cfg.get("enabled_list"))
            logging.getLogger(__name__).info("Controller state reset")

    def health_check(self) -> dict:
        """Perform a health check and return diagnostic information.

        Returns:
            Dictionary with health status and diagnostics.

        Example:
            >>> health = controller.health_check()
            >>> if not health["healthy"]:
            ...     print(f"Issues: {health['issues']}")
        """
        with self._lock:
            issues = []
            warnings = []

            # Check for stuck in HOLD state
            if self._hold_state and self._cooldown_start_time is not None:
                cooldown_duration = time() - self._cooldown_start_time
                if cooldown_duration > 3600:  # 1 hour
                    issues.append(f"Stuck in HOLD for {cooldown_duration:.0f}s")
                elif cooldown_duration > 600:  # 10 minutes
                    warnings.append(f"Extended HOLD duration: {cooldown_duration:.0f}s")

            # Check sensitivity
            if self.sensitivity < 0.2:
                warnings.append(f"Low sensitivity: {self.sensitivity:.3f}")

            # Check desensitization counter
            if self.desens_counter > 0.8 * self.config["max_desens_counter"]:
                warnings.append(
                    f"High desens counter: {self.desens_counter}/{self.config['max_desens_counter']}"
                )

            # Check serotonin level
            if self.serotonin_level > 0.95:
                warnings.append(
                    f"Very high serotonin level: {self.serotonin_level:.3f}"
                )

            # Check config validity
            if self.config["decay_rate"] <= 0 or self.config["decay_rate"] > 1:
                issues.append(f"Invalid decay_rate: {self.config['decay_rate']}")

            return {
                "healthy": len(issues) == 0,
                "issues": issues,
                "warnings": warnings,
                "active_profile": self._active_profile,
                "state": {
                    "serotonin_level": self.serotonin_level,
                    "sensitivity": self.sensitivity,
                    "hold_state": self._hold_state,
                    "desens_counter": self.desens_counter,
                },
                "safety_monitor": self._safety_monitor.state(),
                "metrics": self.get_performance_metrics(),
            }

    def get_performance_metrics(self) -> dict:
        """Get performance and usage statistics.

        Returns:
            Dictionary with performance metrics.

        Example:
            >>> metrics = controller.get_performance_metrics()
            >>> print(f"Total steps: {metrics['step_count']}")
        """
        with self._lock:
            avg_cooldown = 0.0
            if self._veto_count > 0:
                avg_cooldown = self._total_cooldown_time / self._veto_count

            veto_rate = 0.0
            if self._step_count > 0:
                veto_rate = self._veto_count / self._step_count

            return {
                "step_count": self._step_count,
                "veto_count": self._veto_count,
                "veto_rate": veto_rate,
                "total_cooldown_time": self._total_cooldown_time,
                "average_cooldown_duration": avg_cooldown,
                "current_hold_state": self._hold_state,
            }

    def diagnose(self) -> str:
        """Generate a diagnostic report for troubleshooting.

        Returns:
            Formatted diagnostic string.

        Example:
            >>> print(controller.diagnose())
        """
        with self._lock:
            lines = [
                "=== SerotoninController Diagnostic Report ===",
                f"Config: {self.config_path}",
                "",
                "State:",
                f"  Serotonin Level: {self.serotonin_level:.4f}",
                f"  Tonic Level: {self.tonic_level:.4f}",
                f"  Phasic Level: {self.phasic_level:.4f}",
                f"  Gate Level: {self.gate_level:.4f}",
                f"  Sensitivity: {self.sensitivity:.4f}",
                f"  Temperature Floor: {self.temperature_floor:.4f}",
                f"  HOLD State: {self._hold_state}",
                f"  Desens Counter: {self.desens_counter}/{self.config['max_desens_counter']}",
                "",
                "Thresholds:",
                f"  Cooldown Threshold: {self.config['cooldown_threshold']:.4f}",
                f"  Gate Veto: {self.config['gate_veto']:.4f}",
                f"  Phasic Veto: {self.config['phasic_veto']:.4f}",
                "",
                "Performance Metrics:",
            ]

            metrics = self.get_performance_metrics()
            for key, value in metrics.items():
                if isinstance(value, float):
                    lines.append(f"  {key}: {value:.4f}")
                else:
                    lines.append(f"  {key}: {value}")

            lines.append("")
            health = self.health_check()
            lines.append(f"Health: {'OK' if health['healthy'] else 'ISSUES DETECTED'}")
            if health["issues"]:
                lines.append("Issues:")
                for issue in health["issues"]:
                    lines.append(f"  - {issue}")
            if health["warnings"]:
                lines.append("Warnings:")
                for warning in health["warnings"]:
                    lines.append(f"  - {warning}")

            return "\n".join(lines)

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - save config if modified."""
        if exc_type is None:
            # Normal exit - no action needed
            pass
        return False  # Don't suppress exceptions

    def __repr__(self) -> str:
        """String representation for debugging."""
        return (
            f"SerotoninController(config='{self.config_path}', "
            f"level={self.serotonin_level:.3f}, "
            f"hold={self._hold_state}, "
            f"steps={self._step_count})"
        )


if __name__ == "__main__":  # pragma: no cover - utility for documentation
    schema = SerotoninConfig.model_json_schema()
    print(json.dumps(schema, indent=2))
    print()
    print(_generate_config_table(schema))
