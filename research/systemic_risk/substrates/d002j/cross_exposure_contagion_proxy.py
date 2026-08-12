# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""D-002J-P5 substrate: cross-exposure contagion proxy (contagion-class).

Mechanism (one sentence): a DebtRank-style impact cascade propagates a
seed balance-sheet shock across a max-entropy-RECONSTRUCTED exposure
network (Anand/BIS-style, parameterised from PUBLIC aggregate exposure
literature — NOT real interbank transaction microdata), so that an
initially impaired set drags counterparties' equity down in damped
rounds until the cascade saturates.

This is the CW1/CW2/CW6 contagion channel. Critically, the network is
RECONSTRUCTED from public aggregate statistics; per Brunetti et al.
(e-MID) the physical interbank funding network DOWN-shifts in crisis
while cross-asset correlation networks UP-shift, so this substrate's
reconstructed-network cascade does NOT prove real interbank contagion
and explicitly forbids that claim.

Maps positive control ``PC2_CONTAGION_CASCADE_INJECTION``.
"""

from __future__ import annotations

from typing import Any, Final

import numpy as np
from numpy.typing import NDArray

from research.systemic_risk.substrates.d002j.substrate_base import (
    SCHEMA_SUBSTRATE_INSTANCE,
    SubstrateInstance,
)

SUBSTRATE_ID: Final[str] = "cross_exposure_contagion_proxy"
MECHANISM_FAMILY: Final[str] = "contagion"

_DEFAULT_PARAMS: Final[dict[str, float]] = {
    "n_nodes": 40.0,
    "rounds": 60.0,
    "mean_degree": 6.0,
    "exposure_intensity": 0.18,
    "recovery_rate": 0.4,
    "seed_shock_fraction": 0.1,
    "seed_shock_magnitude": 0.6,
    "damping": 0.85,
}


class CrossExposureContagionProxySubstrate:
    """Generative DebtRank-style contagion substrate (PC2 analogue).

    State variables
    ---------------
    ``equity_loss_fraction`` (per node):
        Cumulative fraction of node equity destroyed by the cascade.
    ``impaired_indicator`` (per node):
        Whether the node has crossed the impairment boundary.
    """

    substrate_id: Final[str] = SUBSTRATE_ID
    mechanism_family: Final[str] = MECHANISM_FAMILY

    def simulate(self, seed: int, params: dict[str, float] | None = None) -> SubstrateInstance:
        """Deterministically simulate a reconstructed-network contagion cascade.

        Same ``seed`` + same ``params`` => bit-identical outputs.
        """
        p: dict[str, float] = {**_DEFAULT_PARAMS, **(params or {})}
        rng = np.random.default_rng(seed)
        n = int(p["n_nodes"])
        rounds = int(p["rounds"])
        if n < 4 or rounds < 4:
            raise ValueError(f"{SUBSTRATE_ID}: need n_nodes>=4 and rounds>=4, got {n},{rounds}")

        # Max-entropy-style reconstructed exposure matrix from public
        # aggregate intensities (NOT real bilateral data): row-stochastic
        # impact weights, sparsified to the target mean degree.
        raw = rng.random((n, n))
        np.fill_diagonal(raw, 0.0)
        keep_prob = min(1.0, p["mean_degree"] / max(1.0, n - 1.0))
        mask = (rng.random((n, n)) < keep_prob).astype(np.float64)
        np.fill_diagonal(mask, 0.0)
        w = raw * mask
        row_sums = w.sum(axis=1, keepdims=True)
        # bounds: zero-degree rows get a neutral 1.0 divisor so the
        # row-normalisation is well-defined (isolated node = no spillover),
        # an economic statement, not a silent numeric repair.
        row_sums = np.where(row_sums > 0.0, row_sums, 1.0)
        impact = (w / row_sums) * p["exposure_intensity"]

        # Seed shock on the most-connected nodes.
        equity_loss = np.zeros(n, dtype=np.float64)
        degree = mask.sum(axis=1)
        n_seed = max(1, int(p["seed_shock_fraction"] * n))
        seed_nodes = np.argsort(-degree)[:n_seed]
        equity_loss[seed_nodes] = p["seed_shock_magnitude"]

        loss_traj = np.zeros((rounds, n), dtype=np.float64)
        impaired_traj = np.zeros((rounds, n), dtype=np.float64)
        for r in range(rounds):
            inflow = impact.T @ equity_loss
            new_loss = equity_loss + p["damping"] * (1.0 - p["recovery_rate"]) * inflow
            # INV-bounds: equity-loss fraction is economically capped at
            # 1.0 (a node cannot lose more than its entire equity) and
            # floored at 0.0 (no negative loss).
            equity_loss = np.clip(new_loss, 0.0, 1.0)
            loss_traj[r] = equity_loss
            impaired_traj[r] = (equity_loss >= 0.3).astype(np.float64)

        cascade_impaired_fraction = impaired_traj.mean(axis=1)
        systemic_loss_index = loss_traj.mean(axis=1)

        state_trajectory: NDArray[Any] = loss_traj
        observable_outputs: dict[str, NDArray[Any]] = {
            "cascade_impaired_fraction": cascade_impaired_fraction,
            "systemic_loss_index": systemic_loss_index,
        }
        metadata: dict[str, Any] = {
            "schema_version": SCHEMA_SUBSTRATE_INSTANCE,
            "mechanism_family": MECHANISM_FAMILY,
            "positive_control_analogue": "PC2_CONTAGION_CASCADE_INJECTION",
            "seed_node_count": int(n_seed),
            "requires_real_interbank_transaction_data": False,
            "forbidden_claim_boundary": (
                "Cascade runs on a RECONSTRUCTED network from public "
                "aggregates. Cross-asset / reconstructed-network contagion "
                "does NOT prove real interbank contagion (Brunetti e-MID: "
                "physical interbank network contracts in crisis). No "
                "real-bank validation; no canonical run."
            ),
        }
        return SubstrateInstance(
            substrate_id=SUBSTRATE_ID,
            seed=seed,
            params=p,
            state_trajectory=state_trajectory,
            observable_outputs=observable_outputs,
            metadata=metadata,
        )
