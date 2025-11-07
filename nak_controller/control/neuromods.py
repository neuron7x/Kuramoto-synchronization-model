"""Neuromodulator utilities."""
from __future__ import annotations

from ..core.state import clip


def dopamine(unexpected_reward: float, beta_DA: float) -> float:
    """Compute dopamine level from unexpected reward."""

    return clip(0.5 + beta_DA * unexpected_reward, 0.0, 1.0)


def noradrenaline(global_vol: float, na_vol_gain: float) -> float:
    """Compute NA level from global volatility."""

    return clip(na_vol_gain * global_vol, 0.0, 1.0)


def serotonin(portfolio_dd: float, ht_dd_gain: float) -> float:
    """Compute serotonin level from portfolio drawdown."""

    return clip(ht_dd_gain * portfolio_dd, 0.0, 1.0)


def acetylcholine(exposure: float, eta_ACh: float) -> float:
    """Compute acetylcholine level from exposure."""

    return clip(0.5 + eta_ACh * exposure, 0.0, 1.0)


def modulate_risk_da(r_tilde: float, DA: float, da_gain: float, r_min: float, r_max: float) -> float:
    """Apply dopamine-based risk modulation."""

    delta = da_gain * (DA - 0.5)
    return clip(r_tilde + delta, r_min, r_max)


def modulate_activity_ach(activity_mult: float, ACh: float) -> float:
    """Apply acetylcholine-based activity modulation."""

    return clip(activity_mult * (0.5 + ACh), 0.25, 1.5)


__all__ = [
    "dopamine",
    "noradrenaline",
    "serotonin",
    "acetylcholine",
    "modulate_risk_da",
    "modulate_activity_ach",
]
