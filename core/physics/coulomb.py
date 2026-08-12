# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""T5 — Coulomb Electrostatic Interaction for Data Ingestion.

Define charge:
    q_i(t) = OFI_i(t) / σ(OFI_i, 30)   # normalised order flow imbalance
    positive charge = net buying pressure
    negative charge = net selling pressure

Coulomb force:
    F_ij = k · q_i · q_j / r_ij²
    r_ij = correlation distance (same metric as T1)
    k = normalisation s.t. |F_ij| ∈ [0, 1]

AUDIT RESOLUTION — sign convention:
    F_ij > 0 (same sign charges) → repulsion.
    In markets: same-direction OFI = momentum, which implies ATTRACTION.
    Therefore we FLIP the sign: F_market = -F_coulomb.

    Attraction (opposite signs) → convergent behaviour.
    Repulsion (same signs in Coulomb) → but in market context same-direction
    flow means co-movement → attraction, so we invert.

Adjacency update:
    A_ij(t) = clip(A_ij(t-1) + α · F_market_ij, 0, 1)
    α = 0.1 (slow adaptation prevents overfitting to noise)
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray


class CoulombInteraction:
    """Coulomb-inspired electrostatic interaction for market networks.

    Parameters
    ----------
    alpha : float
        Learning rate for adjacency update (default 0.1).
    lookback : int
        Lookback for OFI normalisation std (default 30).
    """

    def __init__(self, alpha: float = 0.1, lookback: int = 30) -> None:
        if not 0 < alpha <= 1:
            raise ValueError(f"alpha must be in (0, 1], got {alpha}")
        if lookback < 1:
            raise ValueError(f"lookback must be ≥ 1, got {lookback}")
        self._alpha = alpha
        self._lookback = lookback

    @property
    def alpha(self) -> float:
        return self._alpha

    def compute_charges(self, ofi_matrix: NDArray[np.float64]) -> NDArray[np.float64]:
        """Normalised charges q_i = OFI_i / σ(OFI_i).

        Parameters
        ----------
        ofi_matrix : (T, N) array
            Order flow imbalance time series for N assets.

        Returns
        -------
        (N,) array of current charges.
        """
        ofi = np.asarray(ofi_matrix, dtype=np.float64)
        if ofi.ndim != 2:
            raise ValueError(f"Expected 2-D array (T, N), got ndim={ofi.ndim}")

        tail = ofi[-self._lookback :]
        current = ofi[-1]
        sigma = np.std(tail, axis=0)
        sigma = np.maximum(sigma, 1e-12)
        result: NDArray[np.float64] = current / sigma
        return result

    @staticmethod
    def compute_forces(
        charges: NDArray[np.float64],
        correlation_distances: NDArray[np.float64],
    ) -> NDArray[np.float64]:
        """Compute Coulomb force matrix with market sign convention.

        F_market_ij = -k · q_i · q_j / r_ij²

        The negative sign flips Coulomb convention:
        same-sign OFI → negative F_market → attraction (co-movement).

        Forces are normalised to [-1, 1].
        """
        charges = np.asarray(charges, dtype=np.float64)
        distances = np.asarray(correlation_distances, dtype=np.float64)
        n = charges.shape[0]

        if distances.shape != (n, n):
            raise ValueError(f"distances must be ({n}, {n}), got {distances.shape}")

        charge_product = np.outer(charges, charges)
        dist_safe = np.maximum(
            distances, 1e-6
        )  # INV-FE2: distance floor prevents Coulomb singularity at r→0
        F_coulomb = charge_product / (dist_safe**2)

        # Flip sign: same-direction OFI = market attraction
        F_market = -F_coulomb
        np.fill_diagonal(F_market, 0.0)

        # Normalise to [-1, 1]
        max_abs = np.max(np.abs(F_market))
        if max_abs > 0:
            F_market = F_market / max_abs

        result: NDArray[np.float64] = F_market
        return result

    def update_adjacency(
        self,
        A: NDArray[np.float64],
        forces: NDArray[np.float64],
    ) -> NDArray[np.float64]:
        """Update adjacency matrix with Coulomb forces.

        A_ij(t) = clip(A_ij(t-1) + α · F_ij, 0, 1)

        Parameters
        ----------
        A : (N, N) current adjacency matrix.
        forces : (N, N) normalised force matrix from compute_forces.

        Returns
        -------
        Updated (N, N) adjacency matrix.
        """
        A = np.asarray(A, dtype=np.float64)
        forces = np.asarray(forces, dtype=np.float64)

        if A.shape != forces.shape:
            raise ValueError(f"A and forces must match: {A.shape} vs {forces.shape}")

        A_new = A + self._alpha * forces
        A_new = np.clip(
            A_new, 0.0, 1.0
        )  # INV-K1: adjacency ∈ [0,1] — bounded coupling after force update
        np.fill_diagonal(A_new, 0.0)
        return A_new


__all__ = ["CoulombInteraction"]
