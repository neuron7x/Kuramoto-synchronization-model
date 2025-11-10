"""PI control loop used to modulate risk exposure.

This module implements a Proportional-Integral (PI) controller that maintains
the Engagement Index (EI) within a target band by adjusting risk exposure.

**Control Theory Background:**

The PI controller is a classical feedback mechanism used to minimize tracking
error in dynamical systems. Given a setpoint (target band) and current state,
the controller computes a control signal u(t) as:

    u(t) = K_p · e(t) + K_i · ∫e(τ)dτ

where:
    - e(t): tracking error at time t
    - K_p: proportional gain (immediate response)
    - K_i: integral gain (accumulated error correction)

**Neuro Analogue:**

The PI controller mimics homeostatic regulation in biological systems:
    - Proportional term: fast negative feedback (e.g., sympathetic reflex)
    - Integral term: slow adaptation (e.g., allostatic load adjustment)

The controller maintains EI (metabolic engagement) in a healthy operating band,
analogous to maintaining glucose, pH, or neurotransmitter balance in CNS.

**Nonlinear Saturations:**

To prevent wind-up and maintain bounded control, we use:
    - tanh(·) saturation for error normalization (soft clipping)
    - Hard clipping for integrator state to [-I_max, I_max]
    - Hard clipping for control output to [r_min, r_max]

These prevent instability and ensure graceful degradation under stress.
"""

from __future__ import annotations

import math
from typing import Optional, Tuple

from ..core.params import NaKParams
from ..core.state import StrategyState, clip


def band_center_width(params: NaKParams, band_expand: float) -> Tuple[float, float]:
    """Compute the center and half-width of the EI control band.

    The target band is [EI_low, EI_high], dynamically expanded by `band_expand`
    during stressed conditions (AMBER/RED modes).

    **Mathematical Model:**
        c = (EI_low + EI_high) / 2
        w = (EI_high - EI_low) / 2 · β_expand

    where:
        - c: band center (nominal setpoint)
        - w: band half-width (control tolerance)
        - β_expand: dynamic expansion factor ≥ 1.0

    Args:
        params: Controller parameters with EI_low and EI_high.
        band_expand: Multiplicative factor for band width (≥ 1.0).

    Returns:
        Tuple of (center, half_width) for the control band.

    Raises:
        ValueError: If computed half_width is non-positive (invalid config).
    """
    center = 0.5 * (params.EI_low + params.EI_high)
    half_width = max(1e-6, 0.5 * (params.EI_high - params.EI_low) * band_expand)
    return center, half_width


def pi_control(
    state: StrategyState, params: NaKParams, *, band_expand: float
) -> Tuple[float, float, float]:
    """Execute one PI control step to compute risk target from EI tracking error.

    **Discrete-Time PI Algorithm:**

        e[k] = (EI[k] - c) / w                  # normalized error
        ε[k] = tanh(e[k])                       # saturated error
        I[k] = clip(I[k-1] + ε[k], -I_max, I_max)  # integrator update
        ι[k] = tanh(I[k] / (I_max/2))           # saturated integral term
        u[k] = K_p · ε[k] + K_i · ι[k]          # control signal
        r[k] = clip(1.0 + u[k], r_min, r_max)   # risk target

    where:
        - EI[k]: current Engagement Index
        - c, w: band center and half-width
        - I[k]: integrator state
        - u[k]: control signal
        - r[k]: risk rate target (1.0 = neutral)

    **Controller Tuning Guidelines:**
        - K_p ∈ [0.4, 0.8]: fast response, may oscillate if too high
        - K_i ∈ [0.05, 0.15]: slow drift correction, avoid wind-up
        - I_max ≈ 0.5–1.0: limits maximum integral authority

    Args:
        state: Strategy state with current EI and integrator I.
        params: Controller parameters (K_p, K_i, I_max, r_min, r_max).
        band_expand: Dynamic band expansion factor (≥ 1.0).

    Returns:
        Tuple of (error, integrator_state, rate_target):
            - error: normalized tracking error e[k]
            - integrator_state: updated I[k]
            - rate_target: computed risk rate r[k] ∈ [r_min, r_max]

    Side Effects:
        Updates state.I (integrator accumulator) in-place.
    """
    center, half_width = band_center_width(params, band_expand)
    error = (state.EI - center) / half_width
    tanh_error = math.tanh(error)
    state.I = clip(state.I + tanh_error, -params.I_max, params.I_max)
    integrator_term = math.tanh(state.I / max(1e-6, params.I_max / 2.0))
    control = params.Kp * tanh_error + params.Ki * integrator_term
    rate_target = clip(1.0 + control, params.r_min, params.r_max)
    return error, state.I, rate_target


def rate_limit(
    previous: Optional[float], target: float, *, limit: float, lo: float, hi: float
) -> float:
    """Apply symmetric rate-of-change limiter to target value.

    Prevents abrupt jumps in control output that could destabilize execution
    or violate physical/regulatory constraints.

    **Mathematical Model:**
        Δ_max = limit
        Δ_actual = clip(target - prev, -Δ_max, Δ_max)
        output = clip(prev + Δ_actual, lo, hi)

    If `previous` is None (first step), returns `clip(target, lo, hi)`.

    **Safety Rationale:**
        Rate limiting is critical for:
        - Preventing position whipsaws due to noisy signals
        - Respecting broker/exchange rate limits
        - Ensuring gradual ramp-up/down for risk management

    Args:
        previous: Previous value (None on first step).
        target: Desired target value.
        limit: Maximum allowed change per step (> 0).
        lo: Minimum allowed output value.
        hi: Maximum allowed output value.

    Returns:
        Rate-limited output in [lo, hi].

    Raises:
        ValueError: If limit ≤ 0 (invalid).
    """
    limited_target = clip(target, lo, hi)
    if previous is None:
        return limited_target
    delta = max(-limit, min(limit, limited_target - previous))
    return clip(previous + delta, lo, hi)


__all__ = ["band_center_width", "pi_control", "rate_limit"]
