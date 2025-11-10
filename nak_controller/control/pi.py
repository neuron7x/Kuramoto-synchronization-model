"""Proportional-Integral (PI) control loop for risk exposure modulation.

This module implements a nonlinear PI controller that maintains the engagement
index (EI) within a target band by adjusting the risk multiplier. The controller
uses hyperbolic tangent nonlinearity for bounded error and integrator signals.
"""

from __future__ import annotations

import math
from typing import Optional, Tuple

from ..core.params import NaKParams
from ..core.state import StrategyState, clip

# Numerical stability constant
_EPSILON = 1e-6


def band_center_width(params: NaKParams, band_expand: float) -> Tuple[float, float]:
    """Compute the center and half-width of the EI control band.
    
    The control band defines the target range for the engagement index.
    When EI is within this band, the controller maintains steady-state.
    
    Args:
        params: Controller parameters with EI_low and EI_high bounds
        band_expand: Multiplicative expansion factor for the band width
        
    Returns:
        Tuple of (center, half_width) for the control band
    """
    center = 0.5 * (params.EI_low + params.EI_high)
    half_width = max(_EPSILON, 0.5 * (params.EI_high - params.EI_low) * band_expand)
    return center, half_width


def pi_control(
    state: StrategyState, params: NaKParams, *, band_expand: float
) -> Tuple[float, float, float]:
    """Execute a PI control step for risk modulation.
    
    Implements a nonlinear PI controller with tanh saturation:
    - Proportional term: Kp * tanh(error)
    - Integral term: Ki * tanh(I / (I_max/2))
    - Control output: 1.0 + P + I
    
    The tanh nonlinearity ensures bounded control signals and prevents
    integrator windup while maintaining smooth control action.
    
    Args:
        state: Current strategy state with EI and integrator I
        params: Controller parameters (Kp, Ki, I_max, r_min, r_max)
        band_expand: Band expansion factor for adaptive control
        
    Returns:
        Tuple of (normalized_error, integrator_value, risk_target)
    """
    center, half_width = band_center_width(params, band_expand)
    error = (state.EI - center) / half_width
    tanh_error = math.tanh(error)
    state.I = clip(state.I + tanh_error, -params.I_max, params.I_max)
    integrator_term = math.tanh(state.I / max(_EPSILON, params.I_max / 2.0))
    control = params.Kp * tanh_error + params.Ki * integrator_term
    rate_target = clip(1.0 + control, params.r_min, params.r_max)
    return error, state.I, rate_target


def rate_limit(
    previous: Optional[float], target: float, *, limit: float, lo: float, hi: float
) -> float:
    """Apply a symmetric rate limit to prevent abrupt control changes.
    
    Constrains the rate of change to [-limit, +limit] per step, preventing
    sudden jumps that could destabilize the trading system.
    
    Args:
        previous: Previous value (None for first step)
        target: Desired target value
        limit: Maximum allowed change per step
        lo: Lower bound for output
        hi: Upper bound for output
        
    Returns:
        Rate-limited value within [lo, hi]
    """
    limited_target = clip(target, lo, hi)
    if previous is None:
        return limited_target
    delta = max(-limit, min(limit, limited_target - previous))
    return clip(previous + delta, lo, hi)


__all__ = ["band_center_width", "pi_control", "rate_limit"]
