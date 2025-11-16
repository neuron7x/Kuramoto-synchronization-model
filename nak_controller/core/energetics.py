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
    """Update the neuronal load component based on local observations.

    The load represents the accumulated stress on the trading strategy from
    various operational factors including trade frequency, volatility, drawdowns,
    technical errors, latency, and slippage. Higher load indicates greater
    system strain.

    Args:
        state: Current strategy state to be updated in-place
        params: System parameters defining weights and bounds
        obs: Observation dictionary containing operational metrics
        NA: Noradrenaline level (modulates volatility sensitivity)
        rng: Random number generator for noise injection

    Returns:
        Updated load value L (bounded by L_min and L_max)

    Notes:
        - Noradrenaline (NA) dampens volatility impact via na_scale
        - Noise injection provides stochastic robustness
        - All contributions are weighted and summed
    """
    # Extract and validate observations with safe defaults
    trades = max(0.0, float(obs.get("trades", 0.0)))
    vol_raw = clip(float(obs.get("local_vol", 0.0)), 0.0, 1.0)

    # Modulate volatility by noradrenaline (stress hormone reduces vol sensitivity)
    vol = vol_raw * (1.0 - params.na_scale * NA)

    # Extract operational stress factors
    drawdown = clip(float(obs.get("local_dd", 0.0)), 0.0, 1.0)
    tech_errors = clip(float(obs.get("tech_errors", 0.0)), 0.0, 1.0)
    latency = clip(float(obs.get("latency", 0.0)), 0.0, 1.0)
    slippage = clip(float(obs.get("slippage", 0.0)), 0.0, 1.0)

    # Add stochastic noise scaled by volatility for realism
    noise = float(rng.normal(0.0, params.noise_sigma * max(1e-9, vol_raw)))

    # Compute weighted sum of all load contributors
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

    # Enforce physical bounds on load
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

    Energy represents the system's capacity to maintain operations. It increases
    with profits and glial support, decreases with activity costs, and accumulates
    debt when depleted. The debt mechanism captures energy deficit recovery dynamics.

    Args:
        state: Current strategy state to be updated in-place
        params: System parameters defining gains and bounds
        obs: Observation dictionary containing PnL and operational metrics
        NA: Noradrenaline level (modulates volatility cost)
        DA: Dopamine level (unused in base update, reserved for extensions)
        da_unexp: Unexpected dopamine reward signal (unexpected positive outcomes)

    Returns:
        Updated energy value E (bounded by 0 and E_max)

    Notes:
        - Energy debt accumulates when E would go negative
        - Debt decays slowly (95% retention) and blocks recovery
        - Recovery rate increases as debt is paid off
        - Unexpected rewards provide energy boost via dopamine
    """
    # Extract and normalize profitability signal
    pnl_signal = pnl_norm(
        float(obs.get("pnl", 0.0)), scale=float(obs.get("pnl_scale", 0.01))
    )

    # Extract activity and support metrics
    trades = clip(float(obs.get("trades", 0.0)), 0.0, 1.0)
    vol_raw = clip(float(obs.get("local_vol", 0.0)), 0.0, 1.0)
    vol = vol_raw * (1.0 - params.na_scale * NA)
    glial = clip(float(obs.get("glial_support", 0.0)), 0.0, 1.0)

    # Compute energy change: gains from profit and support, losses from activity
    delta = (
        params.a_p * pnl_signal      # Profit gain
        - params.a_n * trades        # Trading cost
        - params.a_v * vol           # Volatility cost
        + params.a_g * glial         # Support gain
    )

    # Add dopamine-driven unexpected reward bonus
    if da_unexp > 0.0:
        delta += params.a_da * da_unexp

    # Apply energy change with debt accounting
    energy_next = state.E + delta
    if energy_next < 0.0:
        # Accumulate debt when energy would go negative
        state.debt += -energy_next
        energy_next = 0.0
    else:
        # Gradually pay off debt and allow recovery
        state.debt = max(0.0, state.debt * 0.95 - 0.01)
        # Recovery scales inversely with debt burden
        recovery = 0.05 * (1.0 - min(1.0, state.debt))
        energy_next += recovery

    # Enforce upper bound on energy reserves
    state.E = clip(energy_next, 0.0, params.E_max)
    return state.E


def compute_EI(state: StrategyState, params: NaKParams, obs: Dict[str, float]) -> float:
    """Compute the engagement index (EI) from energy, load and profitability.

    The engagement index represents the overall system readiness to execute trades.
    It combines:
    - Energy availability (capacity to act)
    - Inverse load (freedom from stress)
    - Recent profitability (performance feedback)

    High EI (close to 1.0) indicates the system is healthy, unstressed, and
    performing well. Low EI triggers protective measures like suspension.

    Args:
        state: Current strategy state containing E, L values
        params: System parameters for normalization and weighting
        obs: Observation dictionary containing PnL metrics

    Returns:
        Engagement index EI in [0, 1], also stored in state.EI and state.health

    Notes:
        - Energy component: normalized available energy
        - Load component: inverted normalized load (lower load = higher component)
        - PnL component: normalized recent profitability
        - All components are weighted and summed, then clipped to [0, 1]
        - EI drives risk sizing, activity frequency, and suspension decisions
    """
    # Normalize energy to [0, 1] range
    energy_component = state.E / max(1e-9, params.E_max)

    # Normalize and invert load (low load = good)
    load_range = max(1e-9, params.L_max - params.L_min)
    load_component = 1.0 - (state.L - params.L_min) / load_range

    # Extract normalized profitability signal
    pnl_component = pnl_norm(
        float(obs.get("pnl", 0.0)), scale=float(obs.get("pnl_scale", 0.01))
    )

    # Compute weighted engagement index
    state.EI = clip(
        params.u_e * energy_component
        + params.u_l * load_component
        + params.u_p * pnl_component,
        0.0,
        1.0,
    )

    # Mirror EI to health metric for monitoring
    state.health = state.EI
    return state.EI


__all__ = ["update_load", "update_energy", "compute_EI"]
