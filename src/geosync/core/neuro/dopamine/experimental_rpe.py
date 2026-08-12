# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Experimental dopamine RPE extension surface.

This module is intentionally non-invasive: it preserves the canonical TD(0)
identity ``delta = reward + gamma * next_value - value`` as the anchor and adds
optional research layers around it.  Do not route production policy decisions
through these helpers until a separate claim is promoted with backtest evidence
and falsifier tests.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence, Tuple


@dataclass(frozen=True)
class RPEExtensionConfig:
    """Configuration for optional RPE research layers."""

    positive_alpha: float = 0.12
    negative_alpha: float = 0.04
    volatility_penalty: float = 0.0
    drawdown_penalty: float = 0.0
    vigor_gain: float = 0.0
    vigor_min: float = 0.10
    vigor_max: float = 2.00


@dataclass(frozen=True)
class RPEExtensionSurface:
    """Computed outputs for the optional RPE extension surface."""

    canonical_delta: float
    risk_adjusted_delta: float
    distributional_delta: Tuple[float, ...]
    asymmetric_value_update: float
    average_reward_vigor: float


def _require_finite(name: str, value: float) -> float:
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    return value


def _clamp(value: float, lower: float, upper: float) -> float:
    if lower > upper:
        raise ValueError("lower bound must be <= upper bound")
    return min(upper, max(lower, _require_finite("clamp value", value)))


def canonical_td_error(
    reward: float,
    value: float,
    next_value: float,
    discount_gamma: float,
) -> float:
    """Return the canonical TD(0) prediction error without extension logic."""

    reward = _require_finite("reward", float(reward))
    value = _require_finite("value", float(value))
    next_value = _require_finite("next_value", float(next_value))
    discount_gamma = _require_finite("discount_gamma", float(discount_gamma))
    if not 0.0 < discount_gamma <= 1.0:
        raise ValueError("discount_gamma must be in (0, 1]")
    return _require_finite(
        "canonical_delta",
        reward + discount_gamma * next_value - value,
    )


def risk_adjusted_reward(
    reward: float,
    volatility: float,
    drawdown: float,
    *,
    volatility_penalty: float,
    drawdown_penalty: float,
) -> float:
    """Apply non-negative market-risk penalties before a secondary RPE pass."""

    reward = _require_finite("reward", float(reward))
    volatility = abs(_require_finite("volatility", float(volatility)))
    drawdown = abs(_require_finite("drawdown", float(drawdown)))
    volatility_penalty = _require_finite("volatility_penalty", float(volatility_penalty))
    drawdown_penalty = _require_finite("drawdown_penalty", float(drawdown_penalty))
    if volatility_penalty < 0.0 or drawdown_penalty < 0.0:
        raise ValueError("risk penalties must be non-negative")
    return _require_finite(
        "risk_adjusted_reward",
        reward - volatility_penalty * volatility - drawdown_penalty * drawdown,
    )


def distributional_td_error(
    reward_quantiles: Sequence[float],
    value: float,
    next_value: float,
    discount_gamma: float,
) -> Tuple[float, ...]:
    """Project reward quantiles through the canonical affine TD(0) anchor."""

    deltas = tuple(
        canonical_td_error(float(reward), value, next_value, discount_gamma)
        for reward in reward_quantiles
    )
    return deltas


def asymmetric_value_update(
    canonical_delta: float,
    *,
    positive_alpha: float,
    negative_alpha: float,
) -> float:
    """Return an asymmetric learning update while preserving raw delta."""

    canonical_delta = _require_finite("canonical_delta", float(canonical_delta))
    positive_alpha = _require_finite("positive_alpha", float(positive_alpha))
    negative_alpha = _require_finite("negative_alpha", float(negative_alpha))
    if positive_alpha < 0.0 or negative_alpha < 0.0:
        raise ValueError("learning rates must be non-negative")
    alpha = positive_alpha if canonical_delta >= 0.0 else negative_alpha
    return _require_finite("asymmetric_value_update", alpha * canonical_delta)


def average_reward_vigor(
    reward: float,
    average_reward: float,
    *,
    gain: float,
    lower: float,
    upper: float,
) -> float:
    """Map reward-above-baseline to a bounded vigor multiplier."""

    reward = _require_finite("reward", float(reward))
    average_reward = _require_finite("average_reward", float(average_reward))
    gain = _require_finite("gain", float(gain))
    lower = _require_finite("lower", float(lower))
    upper = _require_finite("upper", float(upper))
    if lower <= 0.0:
        raise ValueError("lower vigor bound must be positive")
    return _clamp(1.0 + gain * (reward - average_reward), lower, upper)


def compute_rpe_extension_surface(
    *,
    reward: float,
    value: float,
    next_value: float,
    discount_gamma: float,
    reward_quantiles: Sequence[float] = (),
    volatility: float = 0.0,
    drawdown: float = 0.0,
    average_reward: float = 0.0,
    config: RPEExtensionConfig | None = None,
) -> RPEExtensionSurface:
    """Compute optional RPE layers without mutating DopamineController state."""

    cfg = config or RPEExtensionConfig()
    canonical_delta = canonical_td_error(reward, value, next_value, discount_gamma)
    adjusted_reward = risk_adjusted_reward(
        reward,
        volatility,
        drawdown,
        volatility_penalty=cfg.volatility_penalty,
        drawdown_penalty=cfg.drawdown_penalty,
    )
    risk_delta = canonical_td_error(adjusted_reward, value, next_value, discount_gamma)
    quantile_deltas = distributional_td_error(
        reward_quantiles,
        value,
        next_value,
        discount_gamma,
    )
    update = asymmetric_value_update(
        canonical_delta,
        positive_alpha=cfg.positive_alpha,
        negative_alpha=cfg.negative_alpha,
    )
    vigor = average_reward_vigor(
        reward,
        average_reward,
        gain=cfg.vigor_gain,
        lower=cfg.vigor_min,
        upper=cfg.vigor_max,
    )
    return RPEExtensionSurface(
        canonical_delta=canonical_delta,
        risk_adjusted_delta=risk_delta,
        distributional_delta=quantile_deltas,
        asymmetric_value_update=update,
        average_reward_vigor=vigor,
    )


__all__ = [
    "RPEExtensionConfig",
    "RPEExtensionSurface",
    "asymmetric_value_update",
    "average_reward_vigor",
    "canonical_td_error",
    "compute_rpe_extension_surface",
    "distributional_td_error",
    "risk_adjusted_reward",
]
