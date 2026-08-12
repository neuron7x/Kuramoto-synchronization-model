# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""D-002J-P5 substrate: volatility / credit-spread regime (market/info-class).

Mechanism (one sentence): a latent two-regime (calm vs stressed) process
governs the conditional variance of a market-wide stress index and the
level of a composite financial-stress / credit-spread series, so a
regime switch produces the joint vol-up / spread-widening signature seen
in the market-wide leg of CW1 and the CW4 COVID dash-for-cash.

Parameterised by PUBLIC, P1B-audit-surviving market-wide indices
(CBOE VIX, St. Louis Fed Financial Stress Index, OFR Financial Stress
Index). This is a market-wide / information-class observer; it makes NO
bank-level and NO interbank-contagion claim. Cross-asset co-movement of
these indices is NOT evidence of physical interbank funding contagion
(Brunetti e-MID scope guard).

Maps positive control ``PC4_MARKET_WIDE_VOLATILITY_REGIME_SWITCH``.
"""

from __future__ import annotations

from typing import Any, Final

import numpy as np
from numpy.typing import NDArray

from research.systemic_risk.substrates.d002j.substrate_base import (
    SCHEMA_SUBSTRATE_INSTANCE,
    SubstrateInstance,
)

SUBSTRATE_ID: Final[str] = "volatility_credit_spread_regime"
MECHANISM_FAMILY: Final[str] = "market_wide_stress"

_DEFAULT_PARAMS: Final[dict[str, float]] = {
    "horizon": 320.0,
    "calm_vol": 0.012,
    "stress_vol": 0.045,
    "calm_spread": 0.6,
    "stress_spread": 2.4,
    "regime_onset_frac": 0.55,
    "regime_persistence": 0.97,
    "spread_reversion": 0.06,
}


class VolatilityCreditSpreadRegimeSubstrate:
    """Generative volatility / credit-spread regime substrate (PC4 analogue).

    State variables
    ---------------
    ``regime_indicator``:
        Latent 0 = calm / 1 = stressed regime over time.
    ``credit_spread_level``:
        Mean-reverting composite stress / credit-spread level whose
        target depends on the active regime.
    """

    substrate_id: Final[str] = SUBSTRATE_ID
    mechanism_family: Final[str] = MECHANISM_FAMILY

    def simulate(self, seed: int, params: dict[str, float] | None = None) -> SubstrateInstance:
        """Deterministically simulate a vol/credit-spread regime trajectory.

        Same ``seed`` + same ``params`` => bit-identical outputs.
        """
        p: dict[str, float] = {**_DEFAULT_PARAMS, **(params or {})}
        rng = np.random.default_rng(seed)
        horizon = int(p["horizon"])
        if horizon < 16:
            raise ValueError(f"{SUBSTRATE_ID}: horizon must be >= 16, got {horizon}")
        onset = int(p["regime_onset_frac"] * horizon)

        t = np.arange(horizon)
        regime = (t >= onset).astype(np.float64)
        # Sticky regime: once stressed, persistence keeps it stressed.
        for i in range(onset + 1, horizon):
            if rng.random() > p["regime_persistence"]:
                regime[i] = regime[i - 1]

        vol = np.where(regime > 0.5, p["stress_vol"], p["calm_vol"])
        returns = vol * rng.standard_normal(horizon)
        realised_vol = np.sqrt(np.convolve(returns**2, np.ones(8) / 8.0, mode="same") + 1e-12)

        spread = np.zeros(horizon, dtype=np.float64)
        spread[0] = p["calm_spread"]
        for i in range(1, horizon):
            target = p["stress_spread"] if regime[i] > 0.5 else p["calm_spread"]
            spread[i] = (
                spread[i - 1]
                + p["spread_reversion"] * (target - spread[i - 1])
                + 0.02 * vol[i] * rng.standard_normal()
            )
        # INV-bounds: a credit spread is a non-negative economic level.
        spread = np.maximum(0.0, spread)

        state_trajectory: NDArray[Any] = np.stack([regime, spread], axis=1)
        observable_outputs: dict[str, NDArray[Any]] = {
            "realised_volatility": realised_vol,
            "credit_spread_level": spread,
        }
        metadata: dict[str, Any] = {
            "schema_version": SCHEMA_SUBSTRATE_INSTANCE,
            "mechanism_family": MECHANISM_FAMILY,
            "positive_control_analogue": "PC4_MARKET_WIDE_VOLATILITY_REGIME_SWITCH",
            "regime_onset_index": onset,
            "requires_real_interbank_transaction_data": False,
            "forbidden_claim_boundary": (
                "Market-wide / information-class observer on public "
                "stress indices. Cross-asset vol/spread co-movement does "
                "NOT prove interbank contagion (Brunetti e-MID). No "
                "bank-level validation; no canonical run."
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
