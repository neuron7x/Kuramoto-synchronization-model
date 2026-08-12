# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""T7 — Landauer Bound for Inference Efficiency.

Landauer's principle (PHYSICAL, not metaphor):
    E_erase ≥ k_B · T · ln(2) per bit erased
    At T=300K: E_erase ≥ 2.87 × 10⁻²¹ J per bit

Application to GeoSync inference:
    Each numerical update involves implicit information erasure.
    Entropy generation per step: ΔS = n_params · k_B · ln(2)

Practical constraint:
    Minimise n_active_params per inference cycle.
    Prefer sparse models over dense for same predictive power.

HONEST DOCUMENTATION:
    kT·ln(2) ≈ 3×10⁻²¹ J vs actual GPU: ~10⁻¹² J per op.
    This is 9 orders of magnitude above Landauer limit.
    The Landauer bound is a THEORETICAL FLOOR, not a practical target.
    We use it as: minimise unnecessary computation, track as
    efficiency proxy. The metric is "how far from the physical limit",
    not "we achieve the physical limit".

E=mc² is NOT used. Landauer IS physical.
"""

from __future__ import annotations

import math

import numpy as np
from numpy.typing import ArrayLike

from core.physics.reversible_gate import irreversibility_score

# Physical constants (SI units)
K_BOLTZMANN: float = 1.380649e-23  # J/K (exact, 2019 SI redefinition)
ROOM_TEMPERATURE: float = 300.0  # K
LANDAUER_ENERGY: float = K_BOLTZMANN * ROOM_TEMPERATURE * math.log(2)
# ≈ 2.87 × 10⁻²¹ J per bit erased


class LandauerInferenceProfiler:
    """Track inference efficiency relative to Landauer bound.

    Parameters
    ----------
    T : float
        Operating temperature in Kelvin (default 300K).
    gpu_energy_per_op : float
        Estimated energy per GPU operation in Joules (default 1e-12).
        Typical for modern GPUs (NVIDIA A100: ~0.3 pJ/FLOP).
    """

    def __init__(
        self,
        T: float = ROOM_TEMPERATURE,
        gpu_energy_per_op: float = 1e-12,
    ) -> None:
        if T <= 0:
            raise ValueError(f"Temperature must be > 0, got {T}")
        if gpu_energy_per_op <= 0:
            raise ValueError(f"gpu_energy_per_op must be > 0, got {gpu_energy_per_op}")
        self._T = T
        self._gpu_energy_per_op = gpu_energy_per_op
        self._landauer_per_bit = K_BOLTZMANN * T * math.log(2)

    @property
    def landauer_per_bit(self) -> float:
        """Minimum energy per bit erasure at operating temperature (J)."""
        return self._landauer_per_bit

    def entropy_per_step(self, n_active_params: int) -> float:
        """Entropy generated per inference step (in bits).

        Each parameter update erases ≥ 1 bit of prior information.
        For float32: up to 32 bits per parameter, but effective
        information content is typically much less due to redundancy.
        We use 1 bit per parameter as conservative lower bound.

        Parameters
        ----------
        n_active_params : int
            Number of actively updated parameters.

        Returns
        -------
        Entropy in bits.
        """
        if n_active_params < 0:
            raise ValueError(f"n_active_params must be ≥ 0, got {n_active_params}")
        return float(n_active_params)

    def minimum_energy(self, n_active_params: int) -> float:
        """Landauer minimum energy for given parameter count (Joules).

        E_min = n_params · k_B · T · ln(2)
        """
        return n_active_params * self._landauer_per_bit

    def actual_energy(self, n_active_params: int) -> float:
        """Estimated actual GPU energy for given parameter count (Joules)."""
        return n_active_params * self._gpu_energy_per_op

    def efficiency(self, accuracy: float, n_active_params: int) -> float:
        """Inference efficiency = accuracy / entropy_generated.

        Higher is better: more predictive power per bit of computation.

        Parameters
        ----------
        accuracy : float
            Model predictive accuracy (0-1 scale).
        n_active_params : int
            Number of active parameters.

        Returns
        -------
        Efficiency ratio. Dimensionless.
        """
        entropy = self.entropy_per_step(n_active_params)
        if entropy < 1e-12:
            return float("inf") if accuracy > 0 else 0.0
        return accuracy / entropy

    def landauer_ratio(self, n_active_params: int) -> float:
        """Ratio of actual GPU energy to Landauer minimum.

        Measures how far the hardware operates above the physical limit.
        Typical: ~10⁹ (9 orders of magnitude above Landauer).
        """
        e_min = self.minimum_energy(n_active_params)
        e_actual = self.actual_energy(n_active_params)
        if e_min < 1e-30:
            return float("inf")
        return e_actual / e_min

    def recommend_pruning(
        self,
        param_importances: np.ndarray,
        target_efficiency: float,
        current_accuracy: float,
    ) -> dict[str, float | int]:
        """Recommend parameter pruning for target efficiency.

        Parameters
        ----------
        param_importances : (N,) importance scores (higher = more important).
        target_efficiency : desired efficiency metric.
        current_accuracy : current model accuracy.

        Returns
        -------
        Dict with pruning recommendation.
        """
        importances = np.asarray(param_importances, dtype=np.float64)
        n_total = importances.size

        if n_total == 0:
            return {
                "n_total": 0,
                "n_keep": 0,
                "n_prune": 0,
                "prune_ratio": 0.0,
                "estimated_efficiency": 0.0,
            }

        # Sort by importance (ascending — least important first)
        sorted_idx = np.argsort(importances)

        # Binary search for minimum params that achieve target efficiency
        best_n = n_total
        for n_keep in range(1, n_total + 1):
            # Estimate accuracy loss proportional to pruned importance
            kept = sorted_idx[-n_keep:]
            kept_importance = importances[kept].sum()
            total_importance = importances.sum()
            if total_importance > 0:
                est_accuracy = current_accuracy * (kept_importance / total_importance)
            else:
                est_accuracy = current_accuracy

            eff = self.efficiency(est_accuracy, n_keep)
            if eff >= target_efficiency:
                best_n = n_keep
                break

        return {
            "n_total": n_total,
            "n_keep": best_n,
            "n_prune": n_total - best_n,
            "prune_ratio": (n_total - best_n) / n_total,
            "estimated_efficiency": self.efficiency(current_accuracy, best_n),
        }


# ───────────────────────── Executable falsification facade ─────────────────────────
# Action-cost accounting that binds the Landauer floor and Bennett reversibility
# to the falsification catalog (laws: landauer_nonzero_erasure_cost,
# irreversible_cost_dominance). Irreversibility scoring reuses
# core.physics.reversible_gate.irreversibility_score; the Boltzmann constant
# reuses K_BOLTZMANN above. Nothing here reimplements the existing profiler.

# Proxy penalty (same dimensionless units as base_cost) per unit of
# irreversibility score. Explicit constant, not a magic threshold.
_IRREVERSIBILITY_PENALTY: float = 1.0


def bit_erasure_cost(bits: float, temperature: float) -> float:
    """Landauer floor for erasing ``bits`` bits at ``temperature`` kelvin.

    cost = k_B * T * ln2 * bits. Fails closed on a non-positive/non-finite
    temperature (an undefined thermal context) and on negative bits. For
    ``bits > 0`` and ``T > 0`` the cost is strictly positive — no free erasure.
    """
    if not math.isfinite(temperature) or temperature <= 0.0:
        raise ValueError(
            f"temperature must be finite and > 0 K (undefined thermal context "
            f"otherwise), got {temperature!r}; fail-closed"
        )
    if not math.isfinite(bits) or bits < 0.0:
        raise ValueError(f"bits must be finite and >= 0, got {bits!r}; fail-closed")
    return K_BOLTZMANN * temperature * math.log(2.0) * bits


def action_entropy_delta(before: ArrayLike, after: ArrayLike) -> float:
    """Shannon-entropy change H(after) - H(before) in bits over two distributions.

    Each argument is coerced to a probability vector (non-negative, normalised to
    sum 1). Fails closed on negative mass or zero total mass.
    """
    return _shannon_entropy_bits("after", after) - _shannon_entropy_bits("before", before)


def reversible_baseline(action: dict[str, object]) -> float:
    """Reversible-alternative cost: the action's declared base cost alone."""
    return _base_cost(action)


def irreversible_cost(action: dict[str, object]) -> float:
    """Total irreversible cost = base cost + penalty * irreversibility score.

    The score comes from :func:`reversible_gate.irreversibility_score` over the
    action's ``action_kind`` / ``payload_size`` / ``side_effects``.
    """
    return _base_cost(action) + _IRREVERSIBILITY_PENALTY * _score(action)


def assert_irreversible_dominance(
    irr_cost: float,
    rev_cost: float,
    irreversibility_score_value: float,
) -> None:
    """Fail closed unless ``irr_cost >= rev_cost`` (strict when score > 0).

    Takes the two costs explicitly so a fabricated "free rollback" (a reversible
    baseline claimed below an irreversible cost it could not really achieve) is
    caught: any pair with ``rev_cost > irr_cost``, or an equal pair while the
    irreversibility score is positive, violates.
    """
    for name, value in (("irr_cost", irr_cost), ("rev_cost", rev_cost)):
        if not math.isfinite(value) or value < 0.0:
            raise ValueError(f"{name} must be finite and >= 0, got {value!r}; fail-closed")
    if not math.isfinite(irreversibility_score_value) or not (
        0.0 <= irreversibility_score_value <= 1.0
    ):
        raise ValueError(
            f"irreversibility_score must be in [0,1], got {irreversibility_score_value!r}"
        )
    if rev_cost > irr_cost:
        raise ValueError(
            f"IRREVERSIBLE-COST VIOLATED: reversible baseline {rev_cost} exceeds irreversible "
            f"cost {irr_cost} — a fake free rollback. Required: irr >= rev. Fail-closed."
        )
    if irreversibility_score_value > 0.0 and irr_cost <= rev_cost:
        raise ValueError(
            f"IRREVERSIBLE-COST VIOLATED: score={irreversibility_score_value} > 0 but "
            f"irr_cost {irr_cost} <= rev_cost {rev_cost}; an irreversible action must cost "
            f"strictly more than its reversible baseline. Fail-closed."
        )


def _base_cost(action: dict[str, object]) -> float:
    raw = action.get("base_cost", 0.0)
    value = float(raw) if isinstance(raw, (int, float)) else float("nan")
    if not math.isfinite(value) or value < 0.0:
        raise ValueError(f"action['base_cost'] must be finite and >= 0, got {raw!r}; fail-closed")
    return value


def _score(action: dict[str, object]) -> float:
    kind = action.get("action_kind", "")
    payload = action.get("payload_size", 0)
    side = action.get("side_effects", 0)
    if not isinstance(kind, str):
        raise ValueError("action['action_kind'] must be a string; fail-closed")
    if not isinstance(payload, int) or not isinstance(side, int):
        raise ValueError("action payload_size/side_effects must be ints; fail-closed")
    return irreversibility_score(kind, payload, side)


def _shannon_entropy_bits(name: str, distribution: ArrayLike) -> float:
    probs = np.asarray(distribution, dtype=np.float64)
    if probs.ndim != 1 or probs.size == 0:
        raise ValueError(f"{name} must be a non-empty 1-D distribution; fail-closed")
    if not np.all(np.isfinite(probs)) or np.any(probs < 0.0):
        raise ValueError(f"{name} must be finite and non-negative; fail-closed")
    total = float(probs.sum())
    if total <= 0.0:
        raise ValueError(f"{name} has zero total mass; fail-closed")
    normalised = probs / total
    nonzero = normalised[normalised > 0.0]
    return float(-np.sum(nonzero * np.log2(nonzero)))


__all__ = [
    "LandauerInferenceProfiler",
    "K_BOLTZMANN",
    "ROOM_TEMPERATURE",
    "LANDAUER_ENERGY",
    "bit_erasure_cost",
    "action_entropy_delta",
    "irreversible_cost",
    "reversible_baseline",
    "assert_irreversible_dominance",
]
