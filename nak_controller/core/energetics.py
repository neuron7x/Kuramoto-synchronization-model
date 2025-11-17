"""Neuronal energetics model for adaptive trading system regulation.

This module implements a biologically-inspired energy and load tracking system
for the NaK (Sodium-Potassium) controller. It models metabolic constraints on
trading activity, using energy reserves and neuronal load to regulate strategy
engagement dynamically.

The energetics model provides three core mechanisms:
    1. Load tracking: Accumulates stress from trading activity, volatility,
       drawdowns, and technical issues
    2. Energy dynamics: Manages metabolic reserves with gains from PnL and
       costs from activity, including debt accumulation under deficit
    3. Engagement Index (EI): Composite health score combining energy, load,
       and profitability

Key Functions:
    update_load: Compute neuronal load from market and operational metrics
    update_energy: Update energy reserves with income and expenses
    compute_EI: Calculate engagement index as overall health score

The energy system includes a debt mechanism that accumulates when energy drops
below zero, creating a homeostatic pressure to reduce activity during extended
drawdowns. Noradrenaline (NA) and dopamine (DA) modulators influence the
dynamics to respond to market volatility and unexpected outcomes.

Example:
    >>> state = StrategyState()
    >>> params = NaKParams()
    >>> obs = {"pnl": 0.01, "trades": 5, "local_vol": 0.02}
    >>> update_load(state, params, obs, NA=0.3, rng=rng)
    >>> update_energy(state, params, obs, NA=0.3, DA=0.6, da_unexp=0.1)
    >>> ei = compute_EI(state, params, obs)
"""

from __future__ import annotations

from typing import Dict

import numpy as np

from .metrics import pnl_norm
from .params import NaKParams
from .state import StrategyState, clip


def update_load(
    state: StrategyState,
    params: NaKParams,
    obs: Dict[str, float],
    NA: float,
    *,
    rng: np.random.Generator,
) -> float:
    """Update the neuronal load component based on local observations."""
    trades = max(0.0, float(obs.get("trades", 0.0)))
    vol_raw = clip(float(obs.get("local_vol", 0.0)), 0.0, 1.0)
    vol = vol_raw * (1.0 - params.na_scale * NA)
    drawdown = clip(float(obs.get("local_dd", 0.0)), 0.0, 1.0)
    tech_errors = clip(float(obs.get("tech_errors", 0.0)), 0.0, 1.0)
    latency = clip(float(obs.get("latency", 0.0)), 0.0, 1.0)
    slippage = clip(float(obs.get("slippage", 0.0)), 0.0, 1.0)
    noise = float(rng.normal(0.0, params.noise_sigma * max(1e-9, vol_raw)))

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
    """Update the metabolic energy reserves given observations and modulators."""
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
        state.debt += -energy_next
        energy_next = 0.0
    else:
        state.debt = max(0.0, state.debt * 0.95 - 0.01)
        recovery = 0.05 * (1.0 - min(1.0, state.debt))
        energy_next += recovery

    state.E = clip(energy_next, 0.0, params.E_max)
    return state.E


def compute_EI(state: StrategyState, params: NaKParams, obs: Dict[str, float]) -> float:
    """Compute the engagement index (EI) from energy, load and profitability."""
    energy_component = state.E / max(1e-9, params.E_max)
    load_component = 1.0 - (state.L - params.L_min) / max(
        1e-9, (params.L_max - params.L_min)
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
