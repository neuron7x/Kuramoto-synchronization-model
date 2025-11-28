"""Neuromodulator-inspired transforms used by the controller.

This module implements neuromodulator dynamics inspired by neuroscience:

- **Dopamine (DA)**: Reward prediction signal, modulates risk-seeking behavior
- **Noradrenaline (NA)**: Arousal/alertness, responds to volatility
- **Serotonin (5-HT)**: Inhibitory signal, responds to drawdowns
- **Acetylcholine (ACh)**: Attention/activity modulator, scales engagement
- **Glutamate-GABA balance**: Excitatory-inhibitory balance for stability

Key improvements in v2:
- Cross-modulator interaction for realistic neural dynamics
- Adaptive gain based on market regime (glutamate_gaba_balance)
- Homeostatic compensation to prevent extreme states
- Non-linear activation functions for biological plausibility (enhanced variants)
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from ..core.state import clip


# =============================================================================
# Core Neuromodulator Functions (backward compatible)
# =============================================================================


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


# =============================================================================
# Enhanced Neuromodulator Functions (improved neural dynamics)
# =============================================================================


def dopamine_enhanced(unexpected_reward: float, beta_DA: float) -> float:
    """Map unexpected reward into a dopamine-like scalar with enhanced dynamics.

    Uses a tanh-based transform for bounded asymmetric response:
    - Positive surprises (better than expected) → increased DA
    - Negative surprises → decreased DA with loss aversion (1.5x impact)

    Args:
        unexpected_reward: Difference between actual and expected reward
        beta_DA: Gain parameter controlling sensitivity

    Returns:
        Dopamine level in [0, 1], baseline at 0.5
    """
    # Apply asymmetric scaling: losses have 1.5x impact (loss aversion)
    if unexpected_reward < 0:
        scaled = beta_DA * unexpected_reward * 1.5
    else:
        scaled = beta_DA * unexpected_reward
    # Use tanh for smooth saturation at extremes
    return clip(0.5 + 0.5 * math.tanh(scaled), 0.0, 1.0)


def noradrenaline_enhanced(global_vol: float, na_vol_gain: float) -> float:
    """Map global volatility into noradrenaline with Weber-Fechner dynamics.

    Uses square-root transform for diminishing returns at high volatility
    (Weber-Fechner law), preventing over-reaction to extreme conditions.

    Args:
        global_vol: Global market volatility measure in [0, 1]
        na_vol_gain: Gain parameter controlling sensitivity

    Returns:
        Noradrenaline level in [0, 1]
    """
    vol_clamped = max(0.0, min(1.0, global_vol))
    return clip(math.sqrt(vol_clamped) * na_vol_gain, 0.0, 1.0)


def serotonin_enhanced(portfolio_dd: float, ht_dd_gain: float) -> float:
    """Map portfolio drawdown into serotonin with progressive response.

    Uses quadratic response for progressive inhibition under stress:
    small drawdowns have minimal effect, large drawdowns trigger strong inhibition.

    Args:
        portfolio_dd: Portfolio drawdown magnitude in [0, 1]
        ht_dd_gain: Gain parameter controlling sensitivity

    Returns:
        Serotonin level in [0, 1], higher = more inhibition
    """
    dd_clamped = max(0.0, min(1.0, portfolio_dd))
    # Quadratic response: small DD → minimal effect, large DD → strong inhibition
    progressive = dd_clamped + 0.5 * dd_clamped * dd_clamped
    return clip(progressive * ht_dd_gain, 0.0, 1.0)


def glutamate_gaba_balance(
    DA: float,
    NA: float,
    HT: float,
    *,
    excitatory_weight: float = 0.6,
    inhibitory_weight: float = 0.4,
) -> float:
    """Compute excitatory-inhibitory balance from neuromodulator state.

    Models the glutamate (excitatory) vs GABA (inhibitory) balance that
    determines overall neural activity level. High DA and NA increase
    excitation, while high serotonin increases inhibition.

    This balance metric helps coordinate the controller's response by
    providing a unified signal that integrates multiple modulators.

    Args:
        DA: Dopamine level [0, 1]
        NA: Noradrenaline level [0, 1]
        HT: Serotonin level [0, 1]
        excitatory_weight: Weight for excitatory components
        inhibitory_weight: Weight for inhibitory component

    Returns:
        Balance in [-1, 1]: positive = excitatory, negative = inhibitory
    """
    # Excitatory drive from dopamine and noradrenaline
    excitatory = excitatory_weight * ((DA - 0.5) + 0.5 * (NA - 0.5))
    # Inhibitory drive from serotonin
    inhibitory = inhibitory_weight * (HT - 0.5)
    # Net balance
    balance = excitatory - inhibitory
    return clip(balance, -1.0, 1.0)


def cross_modulator_interaction(
    DA: float,
    NA: float,
    HT: float,
    ACh: float,
) -> tuple[float, float, float, float]:
    """Apply cross-modulator interactions for realistic neural dynamics.

    Neuromodulators influence each other in the brain. This function
    models key interactions:
    - High NA enhances DA signaling (stress increases reward sensitivity)
    - High 5-HT dampens DA effect (serotonin opposes dopamine)
    - High DA reduces 5-HT effect (reward counteracts inhibition)
    - ACh modulates the interaction strength (attention gating)

    Args:
        DA: Raw dopamine level [0, 1]
        NA: Raw noradrenaline level [0, 1]
        HT: Raw serotonin level [0, 1]
        ACh: Acetylcholine level [0, 1]

    Returns:
        Tuple of adjusted (DA, NA, HT, ACh) levels
    """
    # Interaction coefficients (biologically inspired, small magnitudes)
    na_to_da = 0.15  # NA enhances DA signaling
    ht_to_da = -0.12  # 5-HT dampens DA
    da_to_ht = -0.10  # DA reduces 5-HT effect
    ach_gate = 0.5 + 0.5 * ACh  # ACh gates interaction strength

    # Apply interactions with ACh-dependent gating
    DA_adj = clip(DA + ach_gate * (na_to_da * (NA - 0.5) + ht_to_da * (HT - 0.5)), 0.0, 1.0)
    HT_adj = clip(HT + ach_gate * da_to_ht * (DA - 0.5), 0.0, 1.0)

    # NA and ACh remain unchanged by other modulators
    return (DA_adj, NA, HT_adj, ACh)


def homeostatic_compensation(
    current: float,
    target: float = 0.5,
    *,
    rate: float = 0.1,
) -> float:
    """Apply homeostatic pressure toward a target baseline.

    Prevents extreme neuromodulator states by gently pulling values
    toward a homeostatic setpoint, similar to biological homeostasis.

    Args:
        current: Current neuromodulator level
        target: Target baseline (default 0.5)
        rate: Compensation rate (higher = faster return to baseline)

    Returns:
        Adjusted level with homeostatic compensation applied
    """
    deviation = current - target
    compensation = -rate * deviation * abs(deviation)  # Quadratic pull
    return clip(current + compensation, 0.0, 1.0)


def modulate_risk_da(
    rate: float, DA: float, da_gain: float, *, r_min: float, r_max: float
) -> float:
    """Adjust the target rate using dopamine.

    High dopamine increases risk appetite (higher rate),
    low dopamine decreases risk appetite (lower rate).

    Args:
        rate: Base risk rate
        DA: Dopamine level [0, 1]
        da_gain: Gain parameter
        r_min: Minimum allowed rate
        r_max: Maximum allowed rate

    Returns:
        Adjusted rate in [r_min, r_max]
    """
    delta = da_gain * (DA - 0.5)
    return clip(rate + delta, r_min, r_max)


def modulate_risk_integrated(
    rate: float,
    DA: float,
    HT: float,
    da_gain: float,
    ht_dampening: float,
    *,
    r_min: float,
    r_max: float,
) -> float:
    """Adjust risk rate using integrated DA-5HT dynamics.

    Combines dopamine's excitatory effect on risk with serotonin's
    inhibitory effect for more balanced risk modulation.

    Args:
        rate: Base risk rate
        DA: Dopamine level [0, 1]
        HT: Serotonin level [0, 1]
        da_gain: Dopamine gain parameter
        ht_dampening: Serotonin dampening parameter
        r_min: Minimum allowed rate
        r_max: Maximum allowed rate

    Returns:
        Adjusted rate in [r_min, r_max]
    """
    # DA increases risk appetite
    da_effect = da_gain * (DA - 0.5)
    # 5-HT dampens risk appetite (inhibitory)
    ht_effect = -ht_dampening * (HT - 0.5)
    # Combined effect
    delta = da_effect + ht_effect
    return clip(rate + delta, r_min, r_max)


def modulate_activity_ach(activity_mult: float, ACh: float) -> float:
    """Scale the activity multiplier via acetylcholine.

    Higher ACh increases engagement/activity level.

    Args:
        activity_mult: Base activity multiplier
        ACh: Acetylcholine level [0, 1]

    Returns:
        Adjusted activity multiplier in [0.25, 1.5]
    """
    return clip(activity_mult * (0.5 + ACh), 0.25, 1.5)


def modulate_activity_integrated(
    activity_mult: float,
    ACh: float,
    NA: float,
    HT: float,
) -> float:
    """Scale activity using integrated ACh-NA-5HT dynamics.

    Combines acetylcholine's attention effect with noradrenaline's
    arousal and serotonin's inhibition for nuanced activity control.

    Args:
        activity_mult: Base activity multiplier
        ACh: Acetylcholine level [0, 1]
        NA: Noradrenaline level [0, 1]
        HT: Serotonin level [0, 1]

    Returns:
        Adjusted activity multiplier in [0.2, 1.6]
    """
    # Base: ACh drives attention/engagement
    ach_factor = 0.5 + ACh
    # NA enhances activity under arousal
    na_boost = 0.1 * (NA - 0.5)
    # 5-HT dampens activity (rest signal)
    ht_dampen = 0.15 * (HT - 0.5)
    # Combined modulation
    combined = ach_factor + na_boost - ht_dampen
    return clip(activity_mult * combined, 0.2, 1.6)


@dataclass
class NeuromodulatorState:
    """Container for complete neuromodulator state with interactions applied."""

    DA: float
    NA: float
    HT: float
    ACh: float
    balance: float
    regime: str

    @classmethod
    def compute(
        cls,
        unexpected_reward: float,
        global_vol: float,
        portfolio_dd: float,
        exposure: float,
        *,
        beta_DA: float,
        na_vol_gain: float,
        ht_dd_gain: float,
        eta_ACh: float,
        apply_interactions: bool = True,
        apply_homeostasis: bool = False,
    ) -> "NeuromodulatorState":
        """Compute complete neuromodulator state from observations.

        Args:
            unexpected_reward: Difference between actual and expected reward
            global_vol: Global market volatility in [0, 1]
            portfolio_dd: Portfolio drawdown magnitude in [0, 1]
            exposure: Current exposure level
            beta_DA: Dopamine gain parameter
            na_vol_gain: Noradrenaline gain parameter
            ht_dd_gain: Serotonin gain parameter
            eta_ACh: Acetylcholine gain parameter
            apply_interactions: Whether to apply cross-modulator interactions
            apply_homeostasis: Whether to apply homeostatic compensation

        Returns:
            Complete NeuromodulatorState with all computations applied
        """
        # Compute raw levels
        DA_raw = dopamine(unexpected_reward, beta_DA)
        NA_raw = noradrenaline(global_vol, na_vol_gain)
        HT_raw = serotonin(portfolio_dd, ht_dd_gain)
        ACh_raw = acetylcholine(exposure, eta_ACh)

        # Apply cross-modulator interactions
        if apply_interactions:
            DA_adj, NA_adj, HT_adj, ACh_adj = cross_modulator_interaction(
                DA_raw, NA_raw, HT_raw, ACh_raw
            )
        else:
            DA_adj, NA_adj, HT_adj, ACh_adj = DA_raw, NA_raw, HT_raw, ACh_raw

        # Apply homeostatic compensation if enabled
        if apply_homeostasis:
            DA_adj = homeostatic_compensation(DA_adj)
            HT_adj = homeostatic_compensation(HT_adj)

        # Compute balance
        balance = glutamate_gaba_balance(DA_adj, NA_adj, HT_adj)

        # Determine regime from balance
        if balance > 0.2:
            regime = "excitatory"
        elif balance < -0.2:
            regime = "inhibitory"
        else:
            regime = "balanced"

        return cls(
            DA=DA_adj,
            NA=NA_adj,
            HT=HT_adj,
            ACh=ACh_adj,
            balance=balance,
            regime=regime,
        )


__all__ = [
    # Core functions (backward compatible)
    "dopamine",
    "noradrenaline",
    "serotonin",
    "acetylcholine",
    # Enhanced functions (improved dynamics)
    "dopamine_enhanced",
    "noradrenaline_enhanced",
    "serotonin_enhanced",
    # Cross-modulator dynamics
    "glutamate_gaba_balance",
    "cross_modulator_interaction",
    "homeostatic_compensation",
    # Modulation functions
    "modulate_risk_da",
    "modulate_risk_integrated",
    "modulate_activity_ach",
    "modulate_activity_integrated",
    # State container
    "NeuromodulatorState",
]
