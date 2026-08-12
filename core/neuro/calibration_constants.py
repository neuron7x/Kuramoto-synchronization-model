# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Calibration constants and parameter ranges for all GeoSync controllers.

This module serves as the single source of truth for all parameter ranges,
thresholds, and calibration boundaries across the GeoSync system. All
controllers should reference these constants for validation and calibration.

The constants are organized by controller type and follow the principle:
- All numeric ranges are inclusive unless otherwise specified
- Invariant relationships (e.g., low < high) are documented and enforced
- No magic numbers in controller logic - everything references this module
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Tuple

__all__ = [
    "NAKParameterRanges",
    "DopamineParameterRanges",
    "SerotoninParameterRanges",
    "RiskEngineParameterRanges",
    "RegimeAdaptiveParameterRanges",
    "RateLimiterParameterRanges",
    "GABAParameterRanges",
    "DesensitizationParameterRanges",
    "validate_parameter_invariants",
]


@dataclass(frozen=True)
class NAKParameterRanges:
    """Parameter ranges for NAK (Neuro-Arousal-Ketosis) Controller.

    The NAK controller manages energy, load, and engagement to determine
    trading activity levels through engagement index thresholds and risk
    multipliers.

    Invariants:
        - 0 <= EI_crit <= EI_low < EI_high <= 1.0
        - 0 <= vol_amber <= vol_red
        - 0 <= dd_amber <= dd_red <= 1.0
        - 0 < delta_r_limit <= 1.0
        - r_min < r_max
        - All risk/activity multipliers >= 0
    """

    # Engagement Index thresholds
    EI_RANGE: Tuple[float, float] = (0.0, 1.0)
    EI_LOW_DEFAULT: float = 0.35
    EI_HIGH_DEFAULT: float = 0.65
    EI_CRIT_DEFAULT: float = 0.15
    EI_HYSTERESIS_RANGE: Tuple[float, float] = (0.0, 0.2)
    EI_HYSTERESIS_DEFAULT: float = 0.05

    # Volatility thresholds (normalized units)
    VOL_RANGE: Tuple[float, float] = (0.0, 2.0)
    VOL_AMBER_DEFAULT: float = 0.70
    VOL_RED_DEFAULT: float = 0.90

    # Drawdown thresholds (0-1 range, fraction of max)
    DD_RANGE: Tuple[float, float] = (0.0, 1.0)
    DD_AMBER_DEFAULT: float = 0.40
    DD_RED_DEFAULT: float = 0.70

    # Rate limiting
    DELTA_R_RANGE: Tuple[float, float] = (0.0, 1.0)
    DELTA_R_LIMIT_DEFAULT: float = 0.20

    # Risk parameter ranges
    R_MIN_DEFAULT: float = 0.0
    R_MAX_DEFAULT: float = 1.0

    # Multipliers range (0-2 typical, but can be higher)
    MULTIPLIER_RANGE: Tuple[float, float] = (0.0, 3.0)
    RISK_MULT_GREEN_DEFAULT: float = 1.00
    RISK_MULT_AMBER_DEFAULT: float = 0.65
    RISK_MULT_RED_DEFAULT: float = 0.00
    ACTIVITY_MULT_GREEN_DEFAULT: float = 1.20
    ACTIVITY_MULT_AMBER_DEFAULT: float = 0.90
    ACTIVITY_MULT_RED_DEFAULT: float = 0.60


@dataclass(frozen=True)
class DopamineParameterRanges:
    """Parameter ranges for Dopamine Controller.

    The dopamine controller implements reward prediction error (RPE) and
    action selection with exploration/exploitation balance.

    Invariants:
        - 0 < discount_gamma < 1.0
        - learning_rate_v > 0
        - burst_factor >= 1.0
        - base_temperature > 0
        - min_temperature >= 0
        - min_temperature <= base_temperature
        - 0 <= invigoration_threshold <= 1.0
        - 0 <= no_go_threshold <= 1.0
        - 0 <= hold_threshold <= 1.0
    """

    # Temporal difference learning
    DISCOUNT_GAMMA_RANGE: Tuple[float, float] = (0.0, 1.0)
    DISCOUNT_GAMMA_DEFAULT: float = 0.98

    # Learning rates
    LEARNING_RATE_MIN: float = 0.0
    LEARNING_RATE_MAX: float = 1.0
    LEARNING_RATE_V_DEFAULT: float = 0.10

    # Burst amplification
    BURST_FACTOR_MIN: float = 1.0
    BURST_FACTOR_MAX: float = 10.0
    BURST_FACTOR_DEFAULT: float = 2.5

    # Temperature (exploration)
    TEMPERATURE_MIN: float = 0.0
    TEMPERATURE_MAX: float = 5.0
    BASE_TEMPERATURE_DEFAULT: float = 1.0
    MIN_TEMPERATURE_DEFAULT: float = 0.05

    # Gate thresholds
    THRESHOLD_RANGE: Tuple[float, float] = (0.0, 1.0)
    INVIGORATION_THRESHOLD_DEFAULT: float = 0.75
    NO_GO_THRESHOLD_DEFAULT: float = 0.25
    HOLD_THRESHOLD_DEFAULT: float = 0.40

    # Decay and adaptation
    DECAY_RATE_RANGE: Tuple[float, float] = (0.0, 1.0)
    DECAY_RATE_DEFAULT: float = 0.95


@dataclass(frozen=True)
class SerotoninParameterRanges:
    """Parameter ranges for Serotonin Controller.

    The serotonin controller models chronic stress dynamics and produces
    hold decisions for the trading system.

    Invariants:
        - 0 <= tonic_beta <= 1.0
        - 0 <= phasic_beta <= 1.0
        - stress_gain >= 0
        - 0 <= stress_threshold <= 1.5
        - 0 <= release_threshold <= stress_threshold
        - 0 <= hysteresis <= 1.0
        - cooldown_ticks >= 0
        - 0 <= max_desensitization < 1.0
        - 0 <= floor_min <= floor_max <= 1.0
    """

    # EMA decay rates
    BETA_RANGE: Tuple[float, float] = (0.0, 1.0)
    TONIC_BETA_DEFAULT: float = 0.95
    PHASIC_BETA_DEFAULT: float = 0.70

    # Gain factors
    GAIN_MIN: float = 0.0
    STRESS_GAIN_DEFAULT: float = 1.0
    DRAWDOWN_GAIN_DEFAULT: float = 0.5
    NOVELTY_GAIN_DEFAULT: float = 0.3
    FLOOR_GAIN_DEFAULT: float = 2.0

    # Thresholds
    STRESS_THRESHOLD_RANGE: Tuple[float, float] = (0.0, 1.5)
    STRESS_THRESHOLD_DEFAULT: float = 0.8
    RELEASE_THRESHOLD_DEFAULT: float = 0.5

    # Hysteresis
    HYSTERESIS_RANGE: Tuple[float, float] = (0.0, 1.0)
    HYSTERESIS_DEFAULT: float = 0.1

    # Cooldown
    COOLDOWN_TICKS_MIN: int = 0
    COOLDOWN_TICKS_DEFAULT: int = 5
    COOLDOWN_EXTENSION_DEFAULT: int = 3

    # Desensitization
    DESENSITIZATION_RATE_DEFAULT: float = 0.01
    DESENSITIZATION_DECAY_DEFAULT: float = 0.99
    MAX_DESENSITIZATION_RANGE: Tuple[float, float] = (0.0, 0.99)
    MAX_DESENSITIZATION_DEFAULT: float = 0.5

    # Temperature floor
    FLOOR_RANGE: Tuple[float, float] = (0.0, 1.0)
    FLOOR_MIN_DEFAULT: float = 0.1
    FLOOR_MAX_DEFAULT: float = 0.8

    # Chronic stress window
    CHRONIC_WINDOW_MIN: int = 1
    CHRONIC_WINDOW_DEFAULT: int = 20


@dataclass(frozen=True)
class RiskEngineParameterRanges:
    """Parameter ranges for Risk Engine.

    The risk engine enforces hard limits to protect capital through position,
    notional, and rate limits.

    Invariants:
        - max_position_size >= 0
        - max_notional >= 0
        - max_leverage > 0
        - max_daily_loss >= 0
        - 0 < max_daily_loss_percent <= 1.0
        - max_orders_per_minute >= 0
        - max_orders_per_hour >= max_orders_per_minute
        - 0 <= safe_mode_position_multiplier <= 1.0
        - kill_switch_loss_streak >= 1
    """

    # Position limits
    MAX_POSITION_SIZE_DEFAULT: float = 100.0
    MAX_NOTIONAL_DEFAULT: float = 100000.0
    POSITION_SIZE_MIN: float = 0.0

    # Loss limits
    MAX_DAILY_LOSS_DEFAULT: float = 10000.0
    MAX_DAILY_LOSS_PERCENT_RANGE: Tuple[float, float] = (0.0, 1.0)
    MAX_DAILY_LOSS_PERCENT_DEFAULT: float = 0.05  # 5%

    # Exposure limits
    MAX_TOTAL_EXPOSURE_DEFAULT: float = 500000.0
    MAX_LEVERAGE_MIN: float = 0.01
    MAX_LEVERAGE_DEFAULT: float = 5.0
    MAX_LEVERAGE_TYPICAL_MAX: float = 20.0

    # Rate limits
    MAX_ORDERS_PER_MINUTE_MIN: int = 0
    MAX_ORDERS_PER_MINUTE_DEFAULT: int = 60
    MAX_ORDERS_PER_HOUR_DEFAULT: int = 500

    # Kill-switch thresholds
    KILL_SWITCH_LOSS_THRESHOLD_DEFAULT: float = 25000.0
    KILL_SWITCH_LOSS_STREAK_MIN: int = 1
    KILL_SWITCH_LOSS_STREAK_DEFAULT: int = 5
    KILL_SWITCH_LIMIT_MULTIPLIER_RANGE: Tuple[float, float] = (1.0, 2.0)
    KILL_SWITCH_LIMIT_MULTIPLIER_DEFAULT: float = 1.5

    # Safe-mode settings
    SAFE_MODE_POSITION_MULTIPLIER_RANGE: Tuple[float, float] = (0.0, 1.0)
    SAFE_MODE_POSITION_MULTIPLIER_DEFAULT: float = 0.25

    # Threshold factors (used in engine.py)
    CRITICAL_THRESHOLD_FACTOR: float = 0.8  # 80% of max = critical
    WARNING_THRESHOLD_FACTOR: float = 0.5  # 50% of max = warning


@dataclass(frozen=True)
class RegimeAdaptiveParameterRanges:
    """Parameter ranges for Regime Adaptive Exposure Guard.

    Dynamically scales exposure allowances based on realized volatility regimes.

    Invariants:
        - 0 < calm_threshold < stressed_threshold < critical_threshold
        - all multipliers > 0
        - half_life_seconds > 0
        - min_samples >= 1
        - cooldown_seconds >= 0
    """

    # Volatility regime thresholds (absolute return units)
    CALM_THRESHOLD_DEFAULT: float = 0.005
    STRESSED_THRESHOLD_DEFAULT: float = 0.02
    CRITICAL_THRESHOLD_DEFAULT: float = 0.04
    THRESHOLD_MIN: float = 0.001
    THRESHOLD_MAX: float = 0.10

    # Exposure multipliers
    MULTIPLIER_MIN: float = 0.01
    MULTIPLIER_MAX: float = 2.0
    CALM_MULTIPLIER_DEFAULT: float = 1.1
    NORMAL_MULTIPLIER: float = 1.0
    STRESSED_MULTIPLIER_DEFAULT: float = 0.65
    CRITICAL_MULTIPLIER_DEFAULT: float = 0.4

    # EWMA parameters
    HALF_LIFE_SECONDS_MIN: float = 1.0
    HALF_LIFE_SECONDS_DEFAULT: float = 120.0
    MIN_SAMPLES_MIN: int = 1
    MIN_SAMPLES_DEFAULT: int = 5

    # Cooldown
    COOLDOWN_SECONDS_MIN: float = 0.0
    COOLDOWN_SECONDS_DEFAULT: float = 30.0


@dataclass(frozen=True)
class RateLimiterParameterRanges:
    """Parameter ranges for Rate Limiter (API and execution).

    Sliding window rate limiters for API endpoints and order submission.

    Invariants:
        - limit > 0
        - window_seconds > 0
    """

    # Rate limits
    LIMIT_MIN: int = 1
    LIMIT_DEFAULT: int = 100
    LIMIT_MAX: int = 10000

    # Window duration
    WINDOW_SECONDS_MIN: float = 1.0
    WINDOW_SECONDS_DEFAULT: float = 60.0
    WINDOW_SECONDS_MAX: float = 3600.0


@dataclass(frozen=True)
class GABAParameterRanges:
    """Parameter ranges for GABA Inhibition Gate.

    The GABA controller provides inhibitory control to prevent impulsive actions.

    Invariants:
        - impulse_threshold >= 0
        - inhibition_strength >= 0
    """

    # Impulse detection
    IMPULSE_THRESHOLD_MIN: float = 0.0
    IMPULSE_THRESHOLD_DEFAULT: float = 0.7
    IMPULSE_THRESHOLD_MAX: float = 2.0

    # Inhibition strength
    INHIBITION_STRENGTH_MIN: float = 0.0
    INHIBITION_STRENGTH_DEFAULT: float = 0.5
    INHIBITION_STRENGTH_MAX: float = 1.0


@dataclass(frozen=True)
class DesensitizationParameterRanges:
    """Parameter ranges for Desensitization/Sensory Habituation.

    Manages receptor desensitization under repeated stimulation.

    Invariants:
        - 0 < min_sensitivity <= max_sensitivity <= 1.0
        - decay_rate >= 0
    """

    # Sensitivity bounds
    MIN_SENSITIVITY_DEFAULT: float = 0.3
    MAX_SENSITIVITY_DEFAULT: float = 1.0
    SENSITIVITY_RANGE: Tuple[float, float] = (0.0, 1.0)

    # Decay parameters
    DECAY_RATE_MIN: float = 0.0
    DECAY_RATE_DEFAULT: float = 0.01


def validate_parameter_invariants(
    controller_type: str, params: Dict[str, Any]
) -> Tuple[bool, list[str]]:
    """Validate parameter invariants for a specific controller type.

    Args:
        controller_type: Type of controller ('nak', 'dopamine', 'serotonin', etc.)
        params: Dictionary of parameter values to validate

    Returns:
        Tuple of (is_valid, list of error messages)

    Examples:
        >>> params = {"EI_low": 0.35, "EI_high": 0.65, "EI_crit": 0.15}
        >>> valid, errors = validate_parameter_invariants("nak", params)
        >>> assert valid and len(errors) == 0
    """
    errors = []

    if controller_type == "nak":
        errors.extend(_validate_nak_invariants(params))
    elif controller_type == "dopamine":
        errors.extend(_validate_dopamine_invariants(params))
    elif controller_type == "serotonin":
        errors.extend(_validate_serotonin_invariants(params))
    elif controller_type == "risk_engine":
        errors.extend(_validate_risk_engine_invariants(params))
    elif controller_type == "regime_adaptive":
        errors.extend(_validate_regime_adaptive_invariants(params))
    elif controller_type == "rate_limiter":
        errors.extend(_validate_rate_limiter_invariants(params))
    elif controller_type == "gaba":
        errors.extend(_validate_gaba_invariants(params))
    elif controller_type == "desensitization":
        errors.extend(_validate_desensitization_invariants(params))
    else:
        errors.append(f"Unknown controller type: {controller_type}")

    return len(errors) == 0, errors


def _validate_nak_invariants(params: Dict[str, Any]) -> list[str]:
    """Validate NAK controller invariants."""
    errors = []

    # EI threshold relationships
    if "EI_low" in params and "EI_high" in params:
        if params["EI_low"] >= params["EI_high"]:
            errors.append(f"EI_low ({params['EI_low']}) must be < EI_high ({params['EI_high']})")

    if "EI_crit" in params:
        if "EI_low" in params and params["EI_crit"] > params["EI_low"]:
            errors.append(f"EI_crit ({params['EI_crit']}) must be <= EI_low ({params['EI_low']})")
        ranges = NAKParameterRanges()
        if not (ranges.EI_RANGE[0] <= params["EI_crit"] <= ranges.EI_RANGE[1]):
            errors.append(f"EI_crit ({params['EI_crit']}) must be in range {ranges.EI_RANGE}")

    # Volatility threshold ordering
    if "vol_amber" in params and "vol_red" in params:
        if params["vol_amber"] > params["vol_red"]:
            errors.append(
                f"vol_amber ({params['vol_amber']}) must be <= vol_red ({params['vol_red']})"
            )

    # Drawdown threshold ordering
    if "dd_amber" in params and "dd_red" in params:
        if params["dd_amber"] > params["dd_red"]:
            errors.append(f"dd_amber ({params['dd_amber']}) must be <= dd_red ({params['dd_red']})")

    # Rate limit
    if "delta_r_limit" in params:
        ranges = NAKParameterRanges()
        val = params["delta_r_limit"]
        if not (ranges.DELTA_R_RANGE[0] < val <= ranges.DELTA_R_RANGE[1]):
            errors.append(f"delta_r_limit ({val}) must be in range (0, {ranges.DELTA_R_RANGE[1]}]")

    # r_min < r_max
    if "r_min" in params and "r_max" in params:
        if params["r_min"] >= params["r_max"]:
            errors.append(f"r_min ({params['r_min']}) must be < r_max ({params['r_max']})")

    return errors


def _validate_dopamine_invariants(params: Dict[str, Any]) -> list[str]:
    """Validate Dopamine controller invariants."""
    errors = []
    ranges = DopamineParameterRanges()

    # Discount gamma
    if "discount_gamma" in params:
        val = params["discount_gamma"]
        if not (ranges.DISCOUNT_GAMMA_RANGE[0] < val < ranges.DISCOUNT_GAMMA_RANGE[1]):
            errors.append(
                f"discount_gamma ({val}) must be in range {ranges.DISCOUNT_GAMMA_RANGE} "
                f"(exclusive: value must be strictly greater than {ranges.DISCOUNT_GAMMA_RANGE[0]} "
                f"and strictly less than {ranges.DISCOUNT_GAMMA_RANGE[1]})"
            )

    # Learning rate
    if "learning_rate_v" in params:
        val = params["learning_rate_v"]
        if val <= ranges.LEARNING_RATE_MIN:
            errors.append(f"learning_rate_v ({val}) must be > {ranges.LEARNING_RATE_MIN}")

    # Burst factor
    if "burst_factor" in params:
        val = params["burst_factor"]
        if val < ranges.BURST_FACTOR_MIN:
            errors.append(f"burst_factor ({val}) must be >= {ranges.BURST_FACTOR_MIN}")

    # Temperature
    if "base_temperature" in params:
        val = params["base_temperature"]
        if val <= ranges.TEMPERATURE_MIN:
            errors.append(f"base_temperature ({val}) must be > {ranges.TEMPERATURE_MIN}")

    if "min_temperature" in params and "base_temperature" in params:
        if params["min_temperature"] > params["base_temperature"]:
            errors.append(
                f"min_temperature ({params['min_temperature']}) must be <= "
                f"base_temperature ({params['base_temperature']})"
            )

    # Gate thresholds
    for threshold_name in ["invigoration_threshold", "no_go_threshold", "hold_threshold"]:
        if threshold_name in params:
            val = params[threshold_name]
            if not (ranges.THRESHOLD_RANGE[0] <= val <= ranges.THRESHOLD_RANGE[1]):
                errors.append(f"{threshold_name} ({val}) must be in range {ranges.THRESHOLD_RANGE}")

    return errors


def _validate_serotonin_invariants(params: Dict[str, Any]) -> list[str]:
    """Validate Serotonin controller invariants."""
    errors = []
    ranges = SerotoninParameterRanges()

    # Beta ranges
    for beta_name in ["tonic_beta", "phasic_beta"]:
        if beta_name in params:
            val = params[beta_name]
            if not (ranges.BETA_RANGE[0] <= val <= ranges.BETA_RANGE[1]):
                errors.append(f"{beta_name} ({val}) must be in range {ranges.BETA_RANGE}")

    # Stress thresholds
    if "stress_threshold" in params:
        val = params["stress_threshold"]
        if not (ranges.STRESS_THRESHOLD_RANGE[0] <= val <= ranges.STRESS_THRESHOLD_RANGE[1]):
            errors.append(
                f"stress_threshold ({val}) must be in range {ranges.STRESS_THRESHOLD_RANGE}"
            )

    if "release_threshold" in params and "stress_threshold" in params:
        if params["release_threshold"] > params["stress_threshold"]:
            errors.append(
                f"release_threshold ({params['release_threshold']}) must be <= "
                f"stress_threshold ({params['stress_threshold']})"
            )

    # Desensitization
    if "max_desensitization" in params:
        val = params["max_desensitization"]
        if not (ranges.MAX_DESENSITIZATION_RANGE[0] <= val < ranges.MAX_DESENSITIZATION_RANGE[1]):
            errors.append(f"max_desensitization ({val}) must be in range [0, 1) (less than 1)")

    # Floor
    if "floor_min" in params and "floor_max" in params:
        if params["floor_min"] > params["floor_max"]:
            errors.append(
                f"floor_min ({params['floor_min']}) must be <= floor_max ({params['floor_max']})"
            )

    return errors


def _validate_risk_engine_invariants(params: Dict[str, Any]) -> list[str]:
    """Validate Risk Engine invariants."""
    errors = []
    ranges = RiskEngineParameterRanges()

    # Loss percent
    if "max_daily_loss_percent" in params:
        val = params["max_daily_loss_percent"]
        if not (
            ranges.MAX_DAILY_LOSS_PERCENT_RANGE[0] < val <= ranges.MAX_DAILY_LOSS_PERCENT_RANGE[1]
        ):
            errors.append(f"max_daily_loss_percent ({val}) must be in range (0, 1]")

    # Leverage
    if "max_leverage" in params:
        val = params["max_leverage"]
        if val <= ranges.MAX_LEVERAGE_MIN:
            errors.append(f"max_leverage ({val}) must be > {ranges.MAX_LEVERAGE_MIN}")

    # Order rates
    if "max_orders_per_minute" in params and "max_orders_per_hour" in params:
        if params["max_orders_per_minute"] > params["max_orders_per_hour"]:
            errors.append(
                f"max_orders_per_minute ({params['max_orders_per_minute']}) must be <= "
                f"max_orders_per_hour ({params['max_orders_per_hour']})"
            )

    # Safe mode multiplier
    if "safe_mode_position_multiplier" in params:
        val = params["safe_mode_position_multiplier"]
        if not (
            ranges.SAFE_MODE_POSITION_MULTIPLIER_RANGE[0]
            <= val
            <= ranges.SAFE_MODE_POSITION_MULTIPLIER_RANGE[1]
        ):
            errors.append(
                f"safe_mode_position_multiplier ({val}) must be in range {ranges.SAFE_MODE_POSITION_MULTIPLIER_RANGE}"
            )

    # Kill switch streak
    if "kill_switch_loss_streak" in params:
        val = params["kill_switch_loss_streak"]
        if val < ranges.KILL_SWITCH_LOSS_STREAK_MIN:
            errors.append(
                f"kill_switch_loss_streak ({val}) must be >= {ranges.KILL_SWITCH_LOSS_STREAK_MIN}"
            )

    return errors


def _validate_regime_adaptive_invariants(params: Dict[str, Any]) -> list[str]:
    """Validate Regime Adaptive Guard invariants."""
    errors = []

    # Threshold ordering
    if all(k in params for k in ["calm_threshold", "stressed_threshold", "critical_threshold"]):
        calm = params["calm_threshold"]
        stressed = params["stressed_threshold"]
        critical = params["critical_threshold"]

        if not (calm < stressed < critical):
            errors.append(
                f"Thresholds must satisfy calm < stressed < critical, "
                f"got: calm={calm}, stressed={stressed}, critical={critical}"
            )

    # Positive multipliers
    for mult_name in ["calm_multiplier", "stressed_multiplier", "critical_multiplier"]:
        if mult_name in params:
            val = params[mult_name]
            if val <= 0:
                errors.append(f"{mult_name} ({val}) must be > 0")

    # Positive parameters
    if "half_life_seconds" in params and params["half_life_seconds"] <= 0:
        errors.append("half_life_seconds must be > 0")

    if "min_samples" in params and params["min_samples"] < 1:
        errors.append("min_samples must be >= 1")

    return errors


def _validate_rate_limiter_invariants(params: Dict[str, Any]) -> list[str]:
    """Validate Rate Limiter invariants."""
    errors = []
    ranges = RateLimiterParameterRanges()

    if "limit" in params and params["limit"] < ranges.LIMIT_MIN:
        errors.append(f"limit must be >= {ranges.LIMIT_MIN}")

    if "window_seconds" in params and params["window_seconds"] <= 0:
        errors.append("window_seconds must be > 0")

    return errors


def _validate_gaba_invariants(params: Dict[str, Any]) -> list[str]:
    """Validate GABA controller invariants."""
    errors = []
    ranges = GABAParameterRanges()

    if "impulse_threshold" in params:
        val = params["impulse_threshold"]
        if val < ranges.IMPULSE_THRESHOLD_MIN:
            errors.append(f"impulse_threshold ({val}) must be >= {ranges.IMPULSE_THRESHOLD_MIN}")

    if "inhibition_strength" in params:
        val = params["inhibition_strength"]
        if not (ranges.INHIBITION_STRENGTH_MIN <= val <= ranges.INHIBITION_STRENGTH_MAX):
            errors.append(
                f"inhibition_strength ({val}) must be in range "
                f"[{ranges.INHIBITION_STRENGTH_MIN}, {ranges.INHIBITION_STRENGTH_MAX}]"
            )

    return errors


def _validate_desensitization_invariants(params: Dict[str, Any]) -> list[str]:
    """Validate Desensitization invariants."""
    errors = []
    ranges = DesensitizationParameterRanges()

    if "min_sensitivity" in params and "max_sensitivity" in params:
        if params["min_sensitivity"] > params["max_sensitivity"]:
            errors.append(
                f"min_sensitivity ({params['min_sensitivity']}) must be <= "
                f"max_sensitivity ({params['max_sensitivity']})"
            )

    if "decay_rate" in params and params["decay_rate"] < ranges.DECAY_RATE_MIN:
        errors.append(f"decay_rate must be >= {ranges.DECAY_RATE_MIN}")

    return errors
