# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""D-002J-P5 substrate: funding-liquidity rollover stress (funding-class).

Mechanism (one sentence): short-term liabilities must be rolled over each
period at a market funding rate; when the rollover ratio falls below a
solvency-feasible level the funding gap widens, lifting a funding-stress
index and producing rollover-failure events — exactly the public
repo/SOFR-spread signature seen in CW3 (2019 US repo spike) and the
funding leg of CW1/CW4/CW5.

This is a GENERATIVE model parameterised by PUBLIC, P1B-audit-surviving
observables (NY Fed SOFR, OFR repo dashboard, FED H.15 Treasury spreads).
It does NOT read or require real interbank transaction microdata. Per
Brunetti et al. (e-MID) the physical interbank funding network CONTRACTS
in crisis while public funding-rate spreads SPIKE; this substrate models
the public-spread signature only and makes NO interbank-contagion claim.

Maps positive control ``PC1_LIQUIDITY_SHOCK_INJECTION``.
"""

from __future__ import annotations

from typing import Any, Final

import numpy as np
from numpy.typing import NDArray

from research.systemic_risk.substrates.d002j.substrate_base import (
    SCHEMA_SUBSTRATE_INSTANCE,
    SubstrateInstance,
)

SUBSTRATE_ID: Final[str] = "funding_liquidity_rollover"
MECHANISM_FAMILY: Final[str] = "liquidity_funding"

_DEFAULT_PARAMS: Final[dict[str, float]] = {
    "horizon": 240.0,
    "base_rollover_ratio": 0.985,
    "rollover_solvency_floor": 0.92,
    "funding_rate_baseline": 0.022,
    "funding_rate_stress_jump": 0.030,
    "stress_onset_frac": 0.5,
    "stress_decay": 0.04,
    "noise_scale": 0.0015,
}


class FundingLiquidityRolloverSubstrate:
    """Generative funding-rollover-stress substrate (PC1 analogue).

    State variables
    ---------------
    ``funding_gap``:
        Cumulative shortfall between liabilities due and funding raised
        (normalised; economic meaning = unmet rollover demand).
    ``rollover_ratio``:
        Fraction of maturing short-term funding successfully rolled over
        at the prevailing market funding rate.
    """

    substrate_id: Final[str] = SUBSTRATE_ID
    mechanism_family: Final[str] = MECHANISM_FAMILY

    def simulate(self, seed: int, params: dict[str, float] | None = None) -> SubstrateInstance:
        """Deterministically simulate a funding-rollover-stress trajectory.

        Same ``seed`` + same ``params`` => bit-identical outputs.
        """
        p: dict[str, float] = {**_DEFAULT_PARAMS, **(params or {})}
        rng = np.random.default_rng(seed)
        horizon = int(p["horizon"])
        if horizon < 8:
            raise ValueError(f"{SUBSTRATE_ID}: horizon must be >= 8, got {horizon}")
        onset = int(p["stress_onset_frac"] * horizon)

        t = np.arange(horizon)
        # Funding-rate path: baseline until onset, then a stress jump that
        # decays exponentially (public SOFR/Treasury-spread signature).
        stress_active = (t >= onset).astype(np.float64)
        decay = np.exp(-p["stress_decay"] * np.maximum(0.0, t - onset))
        funding_rate = (
            p["funding_rate_baseline"]
            + p["funding_rate_stress_jump"] * stress_active * decay
            + p["noise_scale"] * rng.standard_normal(horizon)
        )

        # Rollover ratio degrades as the funding rate rises above baseline.
        rate_gap = funding_rate - p["funding_rate_baseline"]
        rollover_ratio = p["base_rollover_ratio"] - 6.0 * np.maximum(0.0, rate_gap)
        # INV-bounds: rollover_ratio is an economic fraction in [0, 1];
        # the clamp encodes "you cannot roll over more than 100% nor a
        # negative fraction", not a numeric band-aid.
        rollover_ratio = np.clip(rollover_ratio, 0.0, 1.0)

        # Funding gap accumulates whenever rollover falls below the
        # solvency-feasible floor (the economic insolvency channel).
        shortfall = np.maximum(0.0, p["rollover_solvency_floor"] - rollover_ratio)
        funding_gap = np.cumsum(shortfall)

        funding_stress_index = rate_gap / max(p["funding_rate_stress_jump"], 1e-9) + shortfall
        # INV-bounds: stress index is a non-negative normalised observable.
        funding_stress_index = np.maximum(0.0, funding_stress_index)
        rollover_failure_count = np.cumsum((shortfall > 0.0).astype(np.float64))

        state_trajectory: NDArray[Any] = np.stack([funding_gap, rollover_ratio], axis=1)
        observable_outputs: dict[str, NDArray[Any]] = {
            "funding_stress_index": funding_stress_index,
            "rollover_failure_count": rollover_failure_count,
        }
        metadata: dict[str, Any] = {
            "schema_version": SCHEMA_SUBSTRATE_INSTANCE,
            "mechanism_family": MECHANISM_FAMILY,
            "positive_control_analogue": "PC1_LIQUIDITY_SHOCK_INJECTION",
            "stress_onset_index": onset,
            "requires_real_interbank_transaction_data": False,
            "forbidden_claim_boundary": (
                "Generative public-spread model. Cross-asset / public "
                "funding-rate signature does NOT prove interbank funding "
                "contagion (Brunetti e-MID: interbank network DOWN while "
                "spreads UP). No real-bank validation; no canonical run."
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
