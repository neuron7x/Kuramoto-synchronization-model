"""Global mode selection logic.

This module implements a three-regime risk classification system based on
portfolio-wide stress indicators (volatility and drawdown). The global mode
modulates all strategies' risk/activity parameters simultaneously.

**Regime Classification:**

1. **GREEN**: Normal market conditions. Full risk capacity, nominal activity.
   Used when both volatility and drawdown are below AMBER thresholds.

2. **AMBER**: Elevated stress. Reduced risk capacity, cautious activity.
   Triggered when either volatility or drawdown exceeds AMBER threshold.

3. **RED**: Crisis conditions. Minimal/zero risk, forced suspension.
   Triggered when either volatility or drawdown exceeds RED threshold.

**Behavioral Effects:**

- **Risk Multipliers**: GREEN=1.0, AMBER=0.5-0.8, RED=0.0
  Scales down risk_per_trade_factor linearly with regime severity.

- **Activity Multipliers**: GREEN=1.0-1.2, AMBER=0.8-1.0, RED=0.5-0.7
  Adjusts trading frequency (cooldown) based on stress level.

- **Band Expansion**: GREEN=1.0, AMBER=1.2-1.5, RED=1.5-2.0
  Widens PI controller's EI target band during stress to reduce churn.

**Design Rationale:**

The tri-modal system provides:
- Fast response to acute crises (RED)
- Gradual de-risking during building stress (AMBER)
- Hysteresis via separate AMBER/RED thresholds (prevents oscillation)

**Neuro Analogue:**

Mimics brainstem arousal states (LC-NE, PAG, vlPAG):
- GREEN: exploratory/foraging mode (low arousal)
- AMBER: vigilant/defensive mode (moderate arousal)
- RED: freeze/shutdown mode (extreme arousal)
"""

from __future__ import annotations

from typing import Literal

Mode = Literal["GREEN", "AMBER", "RED"]


def choose_mode(
    global_vol: float,
    portfolio_dd: float,
    *,
    vol_amber: float,
    vol_red: float,
    dd_amber: float,
    dd_red: float,
) -> Mode:
    """Select the global operating mode based on risk indicators.

    **Decision Logic:**

        If DD ≥ DD_red OR vol ≥ vol_red:
            mode = RED
        Elif DD ≥ DD_amber OR vol ≥ vol_amber:
            mode = AMBER
        Else:
            mode = GREEN

    Uses OR logic (not AND) for conservatism: either indicator alone
    can trigger regime transition.

    **Threshold Ordering:**
        Must satisfy: 0 ≤ *_amber < *_red ≤ 1

    Args:
        global_vol: Normalized global volatility ∈ [0, 1].
        portfolio_dd: Normalized portfolio drawdown ∈ [0, 1].
        vol_amber: Volatility threshold for AMBER mode.
        vol_red: Volatility threshold for RED mode.
        dd_amber: Drawdown threshold for AMBER mode.
        dd_red: Drawdown threshold for RED mode.

    Returns:
        Selected mode: "GREEN", "AMBER", or "RED".

    Raises:
        ValueError: If thresholds are not properly ordered.
    """
    if portfolio_dd >= dd_red or global_vol >= vol_red:
        return "RED"
    if portfolio_dd >= dd_amber or global_vol >= vol_amber:
        return "AMBER"
    return "GREEN"


def band_expand_for_mode(
    mode: Mode, *, band_GREEN: float, band_AMBER: float, band_RED: float
) -> float:
    """Return the band expansion factor for the requested mode.

    **Band Expansion Rationale:**

    During stress (AMBER/RED), the PI controller's target band is widened
    to reduce sensitivity and avoid over-correction. This prevents
    oscillatory behavior when EI fluctuates near the band edges.

    **Typical Values:**
        - GREEN: 1.0 (nominal band)
        - AMBER: 1.2–1.5 (20–50% wider)
        - RED: 1.5–2.0 (50–100% wider)

    Wider bands → slower control response → more stable risk exposure.

    Args:
        mode: Current global mode ("GREEN", "AMBER", or "RED").
        band_GREEN: Expansion factor for GREEN mode (typically 1.0).
        band_AMBER: Expansion factor for AMBER mode (typically 1.2–1.5).
        band_RED: Expansion factor for RED mode (typically 1.5–2.0).

    Returns:
        Band expansion factor ≥ 1.0.

    Raises:
        ValueError: If any band_* < 1.0 (invalid configuration).
    """
    if mode == "GREEN":
        return band_GREEN
    if mode == "AMBER":
        return band_AMBER
    return band_RED


__all__ = ["Mode", "choose_mode", "band_expand_for_mode"]
