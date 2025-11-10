"""Neuromodulator-inspired transforms used by the controller.

This module implements simplified neuromodulator dynamics inspired by the
mammalian CNS. Each function maps observable market/portfolio signals to
normalized modulator levels in [0, 1] that adjust controller behavior.

**Neurophysiological Basis:**

1. **Dopamine (DA)**: Reward prediction error (RPE) signal. In the brain,
   phasic dopamine encodes unexpected rewards/punishments (Schultz et al., 1997).
   Here: DA = 0.5 + β_DA · δ, where δ is the unexpected reward signal.

2. **Noradrenaline (NA)**: Arousal and stress response. NA increases with
   environmental uncertainty/volatility (Aston-Jones & Cohen, 2005).
   Here: NA = γ_NA · σ_global, where σ_global is global volatility.

3. **Serotonin (5-HT)**: Inhibitory signal related to aversive outcomes.
   5-HT suppresses risk-taking during punishment/loss (Cools et al., 2011).
   Here: 5-HT = η_5HT · DD_portfolio, where DD is drawdown magnitude.

4. **Acetylcholine (ACh)**: Attention and sensory gating. ACh modulates
   cortical excitability and focus (Hasselmo & Sarter, 2011).
   Here: ACh = 0.5 + η_ACh · exposure, scaling activity with portfolio exposure.
"""

from __future__ import annotations

from ..core.state import clip


def dopamine(unexpected_reward: float, beta_DA: float) -> float:
    """Compute dopamine level from reward prediction error.

    Maps unexpected reward (positive or negative) into a DA signal in [0, 1].
    Baseline is 0.5 (tonic DA), with phasic modulation by unexpected events.

    **Mathematical Model:**
        DA(δ) = clip(0.5 + β_DA · δ, 0, 1)

    where:
        - δ: unexpected reward signal (positive for surprise gains)
        - β_DA: sensitivity parameter (typical: 0.5–1.0)

    **Neuro Analogue:**
        Mimics phasic dopamine burst/dip from VTA/SNc in response to RPE.

    Args:
        unexpected_reward: Reward prediction error signal.
        beta_DA: Gain parameter for dopamine sensitivity.

    Returns:
        Normalized dopamine level in [0, 1].
    """
    return clip(0.5 + beta_DA * unexpected_reward, 0.0, 1.0)


def noradrenaline(global_vol: float, na_vol_gain: float) -> float:
    """Compute noradrenaline level from global volatility.

    Maps market volatility into an NA arousal signal in [0, 1].
    High volatility → elevated NA → heightened vigilance.

    **Mathematical Model:**
        NA(σ) = clip(γ_NA · σ_global, 0, 1)

    where:
        - σ_global: normalized global volatility [0, 1]
        - γ_NA: gain parameter (typical: 0.8–1.2)

    **Neuro Analogue:**
        LC-NE system response to environmental uncertainty/threat.

    Args:
        global_vol: Normalized global volatility in [0, 1].
        na_vol_gain: Gain parameter for NA response.

    Returns:
        Normalized noradrenaline level in [0, 1].
    """
    return clip(global_vol * na_vol_gain, 0.0, 1.0)


def serotonin(portfolio_dd: float, ht_dd_gain: float) -> float:
    """Compute serotonin (5-HT) inhibitory signal from drawdown.

    Maps portfolio drawdown into a 5-HT level in [0, 1].
    Higher drawdown → elevated 5-HT → suppressed risk-taking.

    **Mathematical Model:**
        5-HT(DD) = clip(η_5HT · DD_portfolio, 0, 1)

    where:
        - DD_portfolio: normalized drawdown [0, 1]
        - η_5HT: gain parameter (typical: 0.8–1.2)

    **Neuro Analogue:**
        Dorsal raphe 5-HT inhibition of reward-seeking during punishment.

    Args:
        portfolio_dd: Normalized portfolio drawdown in [0, 1].
        ht_dd_gain: Gain parameter for 5-HT response.

    Returns:
        Normalized serotonin level in [0, 1].
    """
    return clip(portfolio_dd * ht_dd_gain, 0.0, 1.0)


def acetylcholine(exposure: float, eta_ACh: float) -> float:
    """Compute acetylcholine (ACh) activity modulator from exposure.

    Maps portfolio exposure into an ACh signal in [0, 1].
    Baseline is 0.5, modulated by current exposure level.

    **Mathematical Model:**
        ACh(ξ) = clip(0.5 + η_ACh · ξ, 0, 1)

    where:
        - ξ: portfolio exposure (normalized, can be negative)
        - η_ACh: sensitivity parameter (typical: 0.4–0.8)

    **Neuro Analogue:**
        Basal forebrain cholinergic modulation of cortical attention.

    Args:
        exposure: Normalized portfolio exposure.
        eta_ACh: Gain parameter for ACh sensitivity.

    Returns:
        Normalized acetylcholine level in [0, 1].
    """
    return clip(0.5 + eta_ACh * exposure, 0.0, 1.0)


def modulate_risk_da(
    rate: float, DA: float, da_gain: float, *, r_min: float, r_max: float
) -> float:
    """Modulate risk target using dopamine signal.

    Adjusts the PI controller's risk target based on dopamine level.
    Positive RPE (DA > 0.5) increases risk appetite; negative RPE decreases it.

    **Mathematical Model:**
        r_DA = clip(r + α_DA · (DA - 0.5), r_min, r_max)

    where:
        - r: baseline risk rate from PI controller
        - DA: dopamine level [0, 1]
        - α_DA: gain parameter (typical: 0.2–0.4)

    **Behavioral Effect:**
        Implements "hot hand" bias (increased risk after wins) and
        "loss aversion" (decreased risk after losses) via DA modulation.

    Args:
        rate: Baseline risk rate from PI controller.
        DA: Dopamine level in [0, 1].
        da_gain: Modulation strength parameter.
        r_min: Minimum allowed risk rate.
        r_max: Maximum allowed risk rate.

    Returns:
        Dopamine-modulated risk rate in [r_min, r_max].
    """
    delta = da_gain * (DA - 0.5)
    return clip(rate + delta, r_min, r_max)


def modulate_activity_ach(activity_mult: float, ACh: float) -> float:
    """Modulate activity frequency using acetylcholine signal.

    Scales the base activity multiplier by ACh level to adjust
    trading frequency based on attention/focus state.

    **Mathematical Model:**
        f_ACh = clip(f_base · (0.5 + ACh), 0.25, 1.5)

    where:
        - f_base: base activity multiplier from global mode
        - ACh: acetylcholine level [0, 1]

    **Behavioral Effect:**
        Higher ACh (high exposure) increases vigilance and activity;
        lower ACh (low exposure) reduces monitoring intensity.

    Args:
        activity_mult: Base activity multiplier from global mode.
        ACh: Acetylcholine level in [0, 1].

    Returns:
        Modulated activity multiplier in [0.25, 1.5].
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
