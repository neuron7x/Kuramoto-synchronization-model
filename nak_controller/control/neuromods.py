"""Neuromodulator-inspired transforms used by the controller."""

from __future__ import annotations

from dataclasses import dataclass

from ..core.state import clip


def dopamine(unexpected_reward: float, beta_DA: float) -> float:
    """Map unexpected reward into a dopamine-like scalar."""
    return clip(0.5 + beta_DA * unexpected_reward, 0.0, 1.0)


def noradrenaline(global_vol: float, na_vol_gain: float) -> float:
    """Map global volatility into a noradrenaline activation."""
    return clip(global_vol * na_vol_gain, 0.0, 1.0)


def serotonin(portfolio_dd: float, ht_dd_gain: float) -> float:
    """Map portfolio drawdown into a serotonin-like inhibitory signal."""
    return clip(portfolio_dd * ht_dd_gain, 0.0, 1.0)


def acetylcholine(exposure: float, eta_ACh: float) -> float:
    """Map exposure into an acetylcholine-like activity scaler."""
    return clip(0.5 + eta_ACh * exposure, 0.0, 1.0)


def modulate_risk_da(
    rate: float, DA: float, da_gain: float, *, r_min: float, r_max: float
) -> float:
    """Adjust the target rate using dopamine."""
    delta = da_gain * (DA - 0.5)
    return clip(rate + delta, r_min, r_max)


def modulate_activity_ach(activity_mult: float, ACh: float) -> float:
    """Scale the activity multiplier via acetylcholine."""
    return clip(activity_mult * (0.5 + ACh), 0.25, 1.5)


@dataclass(frozen=True)
class ArousalAttentionResult:
    """Combined noradrenaline/acetylcholine modulation diagnostics."""

    risk_rate: float
    activity_multiplier: float
    noradrenaline_level: float
    acetylcholine_level: float


def apply_arousal_attention_hooks(
    rate: float,
    activity_mult: float,
    *,
    noradrenaline_level: float,
    acetylcholine_level: float,
    r_min: float,
    r_max: float,
    na_scale: float,
    ach_focus_gain: float = 0.2,
) -> ArousalAttentionResult:
    """Adjust risk and activity envelopes using NA/ACh arousal heuristics."""

    na_bias = (noradrenaline_level - 0.5) * 2.0
    rate_adjusted = clip(rate * (1.0 + na_scale * na_bias), r_min, r_max)
    ach_bias = (acetylcholine_level - 0.5) * 2.0
    activity_adjusted = clip(activity_mult * (1.0 + ach_focus_gain * ach_bias), 0.1, 2.0)
    return ArousalAttentionResult(
        risk_rate=rate_adjusted,
        activity_multiplier=activity_adjusted,
        noradrenaline_level=noradrenaline_level,
        acetylcholine_level=acetylcholine_level,
    )


__all__ = [
    "dopamine",
    "noradrenaline",
    "serotonin",
    "acetylcholine",
    "modulate_risk_da",
    "modulate_activity_ach",
    "ArousalAttentionResult",
    "apply_arousal_attention_hooks",
]
