"""Energetic dynamics for the NaK controller.

This module implements the metabolic energy and load dynamics that govern
strategy engagement. Inspired by neuronal bioenergetics, we model:

1. **Load (L)**: Cumulative "neuronal firing cost" from activity, stress,
   volatility, and execution quality degradation.

2. **Energy (E)**: Metabolic reserve available for sustaining operations.
   Depleted by activity, replenished by profitability and "glial support."

3. **Engagement Index (EI)**: Health metric derived from energy, load, and PnL.
   Determines whether the strategy can continue trading or must suspend.

**Neurophysiological Inspiration:**

- **Load**: Analogous to synaptic activity and ATP consumption rate.
  High firing rates (trades), volatility (uncertainty), and errors (stress)
  increase metabolic demand (Attwell & Laughlin, 2001).

- **Energy**: Analogous to glucose/glycogen reserves and mitochondrial capacity.
  PnL acts as "energy intake," glial support as auxiliary metabolism,
  losses/activity as "ATP consumption" (Harris et al., 2012).

- **Debt**: Accumulated energy deficit when reserves hit zero.
  Mimics "energy debt" that must be repaid before full recovery.

**Key Equations:**

    L[k+1] = clip(L[k] + ∑w_i · obs_i + ε[k], L_min, L_max)

    E[k+1] = clip(E[k] + a_p·PnL - a_n·trades - a_v·vol + a_g·glial + recovery, 0, E_max)

    EI[k] = u_e·(E/E_max) + u_l·(1 - L/L_max) + u_p·PnL_norm

where:
    - w_i: load weights for different stressors
    - a_i: energy update coefficients
    - u_i: engagement index weights
    - ε[k]: stochastic noise proportional to volatility
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
    """Update the neuronal load (L) based on local observations and NA modulation.

    **Discrete-Time Load Dynamics:**

        L[k+1] = clip(L[k] + Δ_L[k] + ε[k], L_min, L_max)

    where:
        Δ_L[k] = w_n·trades + w_v·vol' + w_d·DD + w_e·errors + w_l·latency + w_s·slip
        vol' = vol · (1 - α_NA · NA)  # NA-modulated volatility
        ε[k] ~ N(0, σ_noise · vol)    # stochastic fluctuation

    **Component Interpretation:**
        - trades: metabolic cost of frequent position adjustments
        - vol': market uncertainty (NA reduces perceived vol via arousal)
        - DD: stress from local drawdown
        - errors: execution quality degradation
        - latency: information delay cost
        - slip: realized transaction cost

    **Neuro Analogue:**
        Load models cumulative "firing cost" in a neural population.
        High load → fatigue → reduced capacity for new signals.

    Args:
        state: Strategy state with current load L.
        params: Parameters with load weights (w_*) and bounds (L_min, L_max).
        obs: Dictionary of local observations (trades, local_vol, local_dd, etc.).
        NA: Noradrenaline level [0, 1] (modulates volatility perception).
        rng: Random number generator for stochastic noise.

    Returns:
        Updated load L[k+1] ∈ [L_min, L_max].

    Side Effects:
        Updates state.L in-place.
    """
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
    """Update metabolic energy reserves (E) given observations and modulators.

    **Discrete-Time Energy Dynamics:**

        Δ_E[k] = a_p·PnL - a_n·trades - a_v·vol' + a_g·glial [+ a_DA·δ_DA]

        If E[k] + Δ_E[k] < 0:
            debt[k+1] = debt[k] + |E[k] + Δ_E[k]|
            E[k+1] = 0
        Else:
            debt[k+1] = max(0, debt[k]·0.95 - 0.01)
            recovery = 0.05 · (1 - min(1, debt[k+1]))
            E[k+1] = clip(E[k] + Δ_E[k] + recovery, 0, E_max)

    where:
        - PnL: profit/loss signal (normalized)
        - vol': NA-modulated volatility
        - glial: auxiliary "glial support" (e.g., risk-off mode, capital injection)
        - δ_DA: positive unexpected reward (DA boost)
        - debt: accumulated energy deficit (must be repaid)

    **Component Interpretation:**
        - a_p·PnL: energy gain from profitable trades (glucose intake)
        - a_n·trades: energy cost of execution activity (ATP consumption)
        - a_v·vol: energy cost of managing volatility stress
        - a_g·glial: auxiliary metabolic support (regeneration)
        - a_DA·δ_DA: dopamine-gated energy boost from surprise wins

    **Debt Mechanism:**
        When energy hits zero, further losses accumulate as "debt."
        Debt blocks full recovery until repaid via profitability or low activity.
        Models "energy debt" in biological systems (Borbély, 1982).

    **Neuro Analogue:**
        Energy models ATP/glucose reserves in a neural circuit.
        Debt models sleep debt or homeostatic pressure.

    Args:
        state: Strategy state with current energy E and debt.
        params: Parameters with energy coefficients (a_*) and E_max.
        obs: Dictionary of local observations (pnl, trades, local_vol, glial_support).
        NA: Noradrenaline level [0, 1] (modulates volatility cost).
        DA: Dopamine level [0, 1] (not directly used; da_unexp is the signal).
        da_unexp: Unexpected reward signal (positive component for DA boost).

    Returns:
        Updated energy E[k+1] ∈ [0, E_max].

    Side Effects:
        Updates state.E and state.debt in-place.
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
        state.debt += -energy_next
        energy_next = 0.0
    else:
        state.debt = max(0.0, state.debt * 0.95 - 0.01)
        recovery = 0.05 * (1.0 - min(1.0, state.debt))
        energy_next += recovery

    state.E = clip(energy_next, 0.0, params.E_max)
    return state.E


def compute_EI(state: StrategyState, params: NaKParams, obs: Dict[str, float]) -> float:
    """Compute the Engagement Index (EI) from energy, load, and profitability.

    **Engagement Index (EI) Formula:**

        EI[k] = clip(u_e·E_norm + u_l·L_norm + u_p·PnL_norm, 0, 1)

    where:
        E_norm = E / E_max             # normalized energy
        L_norm = 1 - (L - L_min) / (L_max - L_min)  # inverted load
        PnL_norm = (PnL / scale + 1) / 2  # normalized PnL ∈ [0, 1]

    **Interpretation:**
        - EI ∈ [0, 1]: overall "health" or "readiness" of the strategy
        - EI < EI_crit: strategy suspended (insufficient metabolic reserve)
        - EI ∈ [EI_low, EI_high]: nominal operating band (PI controller target)
        - EI > EI_high: excess capacity (controller increases risk)

    **Neuro Analogue:**
        EI models "neuronal population health" or "synaptic efficacy."
        Low EI → reduced responsiveness, high EI → increased plasticity.

    **Design Rationale:**
        - u_e (energy weight): typically dominant (0.5–0.6)
        - u_l (load weight): secondary (0.3–0.4)
        - u_p (PnL weight): small (0.1) to avoid overfitting to recent noise

    Args:
        state: Strategy state with current energy E and load L.
        params: Parameters with weights (u_*) and bounds (E_max, L_min, L_max).
        obs: Dictionary of local observations (pnl, pnl_scale).

    Returns:
        Computed engagement index EI[k] ∈ [0, 1].

    Side Effects:
        Updates state.EI and state.health in-place (health is an alias for EI).
    """
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
