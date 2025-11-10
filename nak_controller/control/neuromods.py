"""Neuromodulator-inspired transforms for adaptive behavior modulation.

This module implements bio-inspired neuromodulators that adapt controller
behavior based on market conditions:
- Dopamine (DA): Reward prediction and unexpected gains
- Noradrenaline (NA): Arousal and volatility response
- Serotonin (5-HT): Inhibition and drawdown sensitivity
- Acetylcholine (ACh): Attention and exposure modulation
"""

from __future__ import annotations

from ..core.state import clip


def dopamine(unexpected_reward: float, beta_DA: float) -> float:
    """Map unexpected reward into a dopamine-like activation signal.
    
    Dopamine encodes reward prediction error, increasing with positive
    surprises and decreasing with negative ones. Centered at 0.5 for
    neutral expectations.
    
    Args:
        unexpected_reward: Reward prediction error (positive or negative)
        beta_DA: Sensitivity gain parameter
        
    Returns:
        Dopamine level in [0, 1]
    """
    return clip(0.5 + beta_DA * unexpected_reward, 0.0, 1.0)


def noradrenaline(global_vol: float, na_vol_gain: float) -> float:
    """Map global volatility into a noradrenaline activation signal.
    
    Noradrenaline represents arousal and vigilance, increasing with market
    volatility to promote cautious behavior in turbulent conditions.
    
    Args:
        global_vol: Normalized global market volatility [0, 1]
        na_vol_gain: Amplification factor for volatility sensitivity
        
    Returns:
        Noradrenaline level in [0, 1]
    """
    return clip(global_vol * na_vol_gain, 0.0, 1.0)


def serotonin(portfolio_dd: float, ht_dd_gain: float) -> float:
    """Map portfolio drawdown into a serotonin-like inhibitory signal.
    
    Serotonin acts as a brake system, increasing with drawdown to
    suppress risky behavior and promote recovery.
    
    Args:
        portfolio_dd: Normalized portfolio drawdown [0, 1]
        ht_dd_gain: Amplification factor for drawdown sensitivity
        
    Returns:
        Serotonin level in [0, 1]
    """
    return clip(portfolio_dd * ht_dd_gain, 0.0, 1.0)


def acetylcholine(exposure: float, eta_ACh: float) -> float:
    """Map exposure into an acetylcholine-like activity modulator.
    
    Acetylcholine regulates attention and processing speed, modulating
    activity based on current market exposure. Centered at 0.5 for
    neutral exposure.
    
    Args:
        exposure: Normalized market exposure level
        eta_ACh: Sensitivity parameter for exposure response
        
    Returns:
        Acetylcholine level in [0, 1]
    """
    return clip(0.5 + eta_ACh * exposure, 0.0, 1.0)


def modulate_risk_da(
    rate: float, DA: float, da_gain: float, *, r_min: float, r_max: float
) -> float:
    """Adjust the target risk rate using dopamine modulation.
    
    Dopamine above 0.5 (positive reward prediction) increases risk taking,
    while dopamine below 0.5 (negative prediction) decreases it.
    
    Args:
        rate: Base risk rate from PI controller
        DA: Dopamine level [0, 1]
        da_gain: Strength of dopamine effect on risk
        r_min: Minimum allowed risk rate
        r_max: Maximum allowed risk rate
        
    Returns:
        Modulated risk rate in [r_min, r_max]
    """
    delta = da_gain * (DA - 0.5)
    return clip(rate + delta, r_min, r_max)


def modulate_activity_ach(activity_mult: float, ACh: float) -> float:
    """Scale the activity multiplier via acetylcholine modulation.
    
    Acetylcholine modulates trading frequency/activity based on attention
    and processing capacity. Higher ACh increases activity.
    
    Args:
        activity_mult: Base activity multiplier from global mode
        ACh: Acetylcholine level [0, 1]
        
    Returns:
        Modulated activity multiplier in [0.25, 1.5]
    """
    return clip(activity_mult * (0.5 + ACh), 0.25, 1.5)


__all__ = [
    "dopamine",
    "noradrenaline",
    "serotonin",
    "acetylcholine",
    "modulate_risk_da",
    "modulate_activity_ach",
]
