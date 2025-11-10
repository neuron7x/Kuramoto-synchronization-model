"""Neuronal energy and load dynamics for the NaK controller.

This module implements bio-inspired metabolic energy accounting and
neuronal load tracking, drawing from computational neuroscience principles.
"""

from __future__ import annotations

from typing import Dict

import numpy as np

from .metrics import pnl_norm
from .params import NaKParams
from .state import StrategyState, clip

# Numerical stability epsilon for divisions
_EPSILON = 1e-9

# Debt recovery constants
_DEBT_DECAY_RATE = 0.95  # Exponential decay rate for energy debt
_DEBT_RECOVERY_RATE = 0.05  # Energy recovery rate when not in debt
_DEBT_FORGIVENESS = 0.01  # Small constant for debt forgiveness per step


def update_load(
    state: StrategyState,
    params: NaKParams,
    obs: Dict[str, float],
    NA: float,
    *,
    rng: np.random.Generator,
) -> float:
    """Update the neuronal load component based on local observations.

    The load represents cumulative stress from trading activity, volatility,
    drawdown, technical errors, latency, and slippage. Noradrenaline (NA)
    modulates volatility sensitivity, implementing an adaptive stress response.

    Args:
        state: Current strategy state containing load L
        params: Controller parameters with weight coefficients
        obs: Local observations dictionary
        NA: Noradrenaline activation level [0, 1]
        rng: NumPy random generator for stochastic noise

    Returns:
        Updated load value clamped to [L_min, L_max]
    """
    trades = max(0.0, float(obs.get("trades", 0.0)))
    vol_raw = clip(float(obs.get("local_vol", 0.0)), 0.0, 1.0)
    vol = vol_raw * (1.0 - params.na_scale * NA)
    drawdown = clip(float(obs.get("local_dd", 0.0)), 0.0, 1.0)
    tech_errors = clip(float(obs.get("tech_errors", 0.0)), 0.0, 1.0)
    latency = clip(float(obs.get("latency", 0.0)), 0.0, 1.0)
    slippage = clip(float(obs.get("slippage", 0.0)), 0.0, 1.0)
    noise = float(rng.normal(0.0, params.noise_sigma * max(_EPSILON, vol_raw)))

    load_next = (
        state.L
        + params.w_n * trades
        + params.w_v * vol
        + params.w_d * drawdown
        + params.w_e * tech_errors
        + params.w_l * latency
        + params.w_s * slippage
        + noise
    )
    state.L = clip(load_next, params.L_min, params.L_max)
    return state.L


def update_energy(
    state: StrategyState,
    params: NaKParams,
    obs: Dict[str, float],
    *,
    NA: float,
    DA: float,
    da_unexp: float,
) -> float:
    """Update the metabolic energy reserves given observations and modulators.

    Energy represents the capacity to continue trading operations. Profits
    replenish energy while trading costs and volatility deplete it. When
    energy goes negative, debt accumulates and must be recovered.

    Args:
        state: Current strategy state with energy E and debt
        params: Controller parameters with energy coefficients
        obs: Local observations dictionary
        NA: Noradrenaline activation level [0, 1]
        DA: Dopamine activation level [0, 1] (not directly used here)
        da_unexp: Unexpected dopamine component for reward prediction

    Returns:
        Updated energy value clamped to [0, E_max]
    """
    pnl_signal = pnl_norm(
        float(obs.get("pnl", 0.0)), scale=float(obs.get("pnl_scale", 0.01))
    )
    trades = clip(float(obs.get("trades", 0.0)), 0.0, 1.0)
    vol_raw = clip(float(obs.get("local_vol", 0.0)), 0.0, 1.0)
    vol = vol_raw * (1.0 - params.na_scale * NA)
    glial = clip(float(obs.get("glial_support", 0.0)), 0.0, 1.0)

    delta = (
        params.a_p * pnl_signal
        - params.a_n * trades
        - params.a_v * vol
        + params.a_g * glial
    )
    if da_unexp > 0.0:
        delta += params.a_da * da_unexp

    energy_next = state.E + delta
    if energy_next < 0.0:
        # Energy went negative: accumulate debt
        state.debt += -energy_next
        energy_next = 0.0
    else:
        # Energy positive: decay debt and add recovery bonus
        state.debt = max(0.0, state.debt * _DEBT_DECAY_RATE - _DEBT_FORGIVENESS)
        recovery = _DEBT_RECOVERY_RATE * (1.0 - min(1.0, state.debt))
        energy_next += recovery

    state.E = clip(energy_next, 0.0, params.E_max)
    return state.E


def compute_EI(state: StrategyState, params: NaKParams, obs: Dict[str, float]) -> float:
    """Compute the engagement index (EI) from energy, load and profitability.

    The engagement index represents the overall health and readiness of the
    trading strategy. It combines:
    - Energy level (metabolic capacity)
    - Inverse load (1 - stress level)
    - Recent profitability

    Args:
        state: Current strategy state with energy E and load L
        params: Controller parameters with EI weight coefficients
        obs: Local observations dictionary with PnL data

    Returns:
        Engagement index in [0, 1], also stored in state.EI and state.health
    """
    energy_component = state.E / max(_EPSILON, params.E_max)
    load_component = 1.0 - (state.L - params.L_min) / max(
        _EPSILON, (params.L_max - params.L_min)
    )
    pnl_component = pnl_norm(
        float(obs.get("pnl", 0.0)), scale=float(obs.get("pnl_scale", 0.01))
    )

    state.EI = clip(
        params.u_e * energy_component
        + params.u_l * load_component
        + params.u_p * pnl_component,
        0.0,
        1.0,
    )
    state.health = state.EI
    return state.EI


__all__ = ["update_load", "update_energy", "compute_EI"]
