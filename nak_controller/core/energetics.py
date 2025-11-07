"""Energetic state updates for the NaK controller."""
from __future__ import annotations

from typing import Dict

import numpy as np

from .metrics import pnl_norm
from .params import NaKParams
from .state import StrategyState, clip


def update_load(state: StrategyState, params: NaKParams, obs: Dict[str, float], NA: float) -> float:
    """Update the synthetic load accumulator ``L``."""

    trades = max(0.0, obs.get("trades", 0.0))
    vol_raw = clip(obs.get("local_vol", 0.0), 0.0, 1.0)
    volatility = vol_raw * (1.0 - params.na_scale * NA)
    drawdown = clip(obs.get("local_dd", 0.0), 0.0, 1.0)
    tech = clip(obs.get("tech_errors", 0.0), 0.0, 1.0)
    latency = clip(obs.get("latency", 0.0), 0.0, 1.0)
    slippage = clip(obs.get("slippage", 0.0), 0.0, 1.0)

    rng = np.random.default_rng(42)
    noise = rng.normal(0.0, params.noise_sigma * max(1e-9, vol_raw))

    updated = (
        state.L
        + params.w_n * trades
        + params.w_v * volatility
        + params.w_d * drawdown
        + params.w_e * tech
        + params.w_l * latency
        + params.w_s * slippage
        + noise
    )
    state.L = clip(updated, params.L_min, params.L_max)
    return state.L


def update_energy(
    state: StrategyState,
    params: NaKParams,
    obs: Dict[str, float],
    NA: float,
    DA: float,
    da_unexpected: float,
) -> float:
    """Update the energy store ``E`` and manage debt regeneration."""

    pnl_signal = pnl_norm(obs.get("pnl", 0.0), scale=obs.get("pnl_scale", 0.01))
    trades = clip(obs.get("trades", 0.0), 0.0, 1.0)
    vol_raw = clip(obs.get("local_vol", 0.0), 0.0, 1.0)
    volatility = vol_raw * (1.0 - params.na_scale * NA)
    glial = clip(obs.get("glial_support", 0.0), 0.0, 1.0)

    delta = (
        params.a_p * pnl_signal
        - params.a_n * trades
        - params.a_v * volatility
        + params.a_g * glial
    )
    if da_unexpected > 0.0:
        delta += params.a_da * da_unexpected

    updated = state.E + delta
    if updated < 0.0:
        state.debt += -updated
        updated = 0.0
    else:
        state.debt = max(0.0, state.debt * 0.95 - 0.01)
        updated += 0.05 * (1.0 - min(1.0, state.debt))

    state.E = clip(updated, 0.0, params.E_max)
    return state.E


def compute_EI(state: StrategyState, params: NaKParams, obs: Dict[str, float]) -> float:
    """Compute the energy index ``EI`` from sub-components."""

    energy_part = state.E / max(1e-9, params.E_max)
    load_part = 1.0 - (state.L - params.L_min) / max(1e-9, (params.L_max - params.L_min))
    pnl_part = pnl_norm(obs.get("pnl", 0.0), scale=obs.get("pnl_scale", 0.01))

    state.EI = clip(
        params.u_e * energy_part + params.u_l * load_part + params.u_p * pnl_part,
        0.0,
        1.0,
    )
    state.health = state.EI
    return state.EI


__all__ = ["update_load", "update_energy", "compute_EI"]
