"""Metrics helpers for neuro-optimization objectives."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

import numpy as np


@dataclass
class BalanceMetrics:
    """Neuromodulator balance health metrics.

    Attributes
    ----------
    dopamine_serotonin_ratio : float
        Ratio of dopamine to serotonin levels
    gaba_excitation_balance : float
        Balance between inhibition and excitation
    arousal_attention_coherence : float
        Coherence between arousal and attention
    overall_balance_score : float
        Composite balance score (0-1, higher is better)
    homeostatic_deviation : float
        Deviation from homeostatic setpoint
    """

    dopamine_serotonin_ratio: float
    gaba_excitation_balance: float
    arousal_attention_coherence: float
    overall_balance_score: float
    homeostatic_deviation: float


def compute_balance_metrics(
    state: Dict[str, float],
    setpoints: Dict[str, float],
    *,
    xp=np,
    dtype: np.dtype | str = np.float32,
) -> BalanceMetrics:
    """Calculate neuromodulator balance metrics.

    Parameters
    ----------
    state : Dict[str, float]
        Current neuromodulator state
    setpoints : Dict[str, float]
        Homeostatic setpoints (expects "da_5ht_ratio" and "excitation_inhibition")
    xp : module, optional
        Array module (numpy or cupy)
    dtype : np.dtype or str, optional
        dtype to use for numeric buffers
    """
    resolved_dtype = np.dtype(dtype)

    def to_array(values: List[float]):
        return xp.asarray(values, dtype=resolved_dtype, order="C")

    # Extract state values with defaults
    da_level, sero_level, gaba_inhib, arousal, attention = to_array(
        [
            state.get('dopamine_level', 0.5),
            state.get('serotonin_level', 0.3),
            state.get('gaba_inhibition', 0.4),
            state.get('na_arousal', 1.0),
            state.get('ach_attention', 0.7),
        ]
    )

    # Calculate ratios
    da_5ht_ratio = da_level / (sero_level + resolved_dtype.type(1e-6))

    # Excitation-inhibition balance (higher dopamine = more excitation)
    excitation = da_level + arousal
    inhibition = gaba_inhib + sero_level
    ei_balance = excitation / (inhibition + resolved_dtype.type(1e-6))

    # Arousal-attention coherence (should be correlated)
    aa_coherence = (
        resolved_dtype.type(1.0)
        - xp.abs(arousal - attention) / resolved_dtype.type(2.0)
    )
    aa_coherence = xp.clip(aa_coherence, 0.0, 1.0)

    # Calculate deviations from setpoints
    da_5ht_dev = xp.abs(da_5ht_ratio - setpoints['da_5ht_ratio']) / setpoints['da_5ht_ratio']
    ei_dev = xp.abs(ei_balance - setpoints['excitation_inhibition']) / setpoints['excitation_inhibition']

    # Overall homeostatic deviation.
    # Formula reference: docs/neuro_optimization_guide.md ("Homeostatic Deviation & Balance Score").
    homeostatic_dev = (da_5ht_dev + ei_dev) / resolved_dtype.type(2.0)
    homeostatic_dev = xp.clip(
        homeostatic_dev, resolved_dtype.type(0.0), xp.inf
    )

    # Overall balance score (inverse of deviation).
    # Formula reference: docs/neuro_optimization_guide.md ("Homeostatic Deviation & Balance Score").
    balance_score = resolved_dtype.type(1.0) / (
        resolved_dtype.type(1.0) + homeostatic_dev
    )
    balance_score = xp.clip(
        balance_score, resolved_dtype.type(0.0), resolved_dtype.type(1.0)
    )

    return BalanceMetrics(
        dopamine_serotonin_ratio=float(da_5ht_ratio),
        gaba_excitation_balance=float(ei_balance),
        arousal_attention_coherence=float(aa_coherence),
        overall_balance_score=float(balance_score),
        homeostatic_deviation=float(homeostatic_dev),
    )


def compute_stability(
    performance_history: List[float],
    history_window: int,
    *,
    xp=np,
    dtype: np.dtype | str = np.float32,
) -> float:
    """Compute stability from recent objective history."""
    resolved_dtype = np.dtype(dtype)
    if len(performance_history) >= history_window > 1:
        recent_perf = performance_history[-history_window:]
        recent_array = xp.asarray(recent_perf, dtype=resolved_dtype)
        mean_perf = xp.mean(recent_array)
        std_perf = xp.std(recent_array)
        epsilon = resolved_dtype.type(1e-6)
        denom = xp.maximum(xp.abs(mean_perf), epsilon)
        stability = resolved_dtype.type(1.0) - std_perf / denom
        return float(xp.clip(stability, 0, 1))

    return 0.5


def compute_objective(
    performance: float,
    balance: BalanceMetrics,
    stability: float,
    *,
    performance_min: float,
    performance_max: float,
    performance_weight: float,
    balance_weight: float,
    stability_weight: float,
    xp=np,
    dtype: np.dtype | str = np.float32,
) -> float:
    """Calculate multi-objective optimization target."""
    resolved_dtype = np.dtype(dtype)
    perf_normalized = float(
        xp.clip(
            (performance - performance_min) / (performance_max - performance_min),
            0,
            1,
        )
    )

    objective = (
        performance_weight * perf_normalized
        + balance_weight * balance.overall_balance_score
        + stability_weight * float(
            xp.clip(
                stability,
                resolved_dtype.type(0.0),
                resolved_dtype.type(1.0),
            )
        )
    )
    return objective
