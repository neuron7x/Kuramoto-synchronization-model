# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""D-002J-P5 — financial-mechanistic substrate candidates v1.

This package holds the THREE admitted financial-mechanistic substrate
candidates for the D-002J systemic-risk study. A *substrate* here is a
mechanism-bearing generative model of a financial network/process whose
observable outputs can be measured against P2 crisis windows and
attacked by P6 nulls. It is NOT an abstract graph aesthetic — every
state variable and parameter carries an explicit economic meaning.

The three admitted substrates (operator-locked selection criterion:
exactly 3, >=1 contagion-class, >=1 funding/liquidity-class, >=1
market/information-class, >=4 of 6 P2 windows collectively covered,
NO substrate requiring real interbank transaction microdata):

* :class:`~research.systemic_risk.substrates.d002j.funding_liquidity_rollover.FundingLiquidityRolloverSubstrate`
  — funding/liquidity-class; maps PC1; reconstructed funding graph
  rollover stress (public repo / SOFR / Treasury-spread observables).
* :class:`~research.systemic_risk.substrates.d002j.cross_exposure_contagion_proxy.CrossExposureContagionProxySubstrate`
  — contagion-class; maps PC2; DebtRank-style cascade on a
  max-entropy-reconstructed exposure network (literature-parameterised,
  NOT real interbank transactions).
* :class:`~research.systemic_risk.substrates.d002j.volatility_credit_spread_regime.VolatilityCreditSpreadRegimeSubstrate`
  — market/information-class; maps PC4; volatility / credit-spread
  regime model on market-wide stress indices.

Discipline boundaries (enforced by tests + commit acceptor):

* All simulation is deterministic (``numpy.random.default_rng(seed)``);
  no wall-clock dependence; no real-data reads.
* Cross-asset coherence != interbank funding proof. Per Brunetti et al.
  (e-MID), correlation networks INCREASE in crisis while the physical
  interbank funding network CONTRACTS; these substrates are
  cross-asset / public-source generative models and do NOT prove
  interbank contagion or real-bank systemic risk.
* No canonical run is authorised by this package (P8 territory).
"""

from __future__ import annotations

from research.systemic_risk.substrates.d002j.cross_exposure_contagion_proxy import (
    CrossExposureContagionProxySubstrate,
)
from research.systemic_risk.substrates.d002j.funding_liquidity_rollover import (
    FundingLiquidityRolloverSubstrate,
)
from research.systemic_risk.substrates.d002j.substrate_base import SubstrateInstance
from research.systemic_risk.substrates.d002j.volatility_credit_spread_regime import (
    VolatilityCreditSpreadRegimeSubstrate,
)

__all__ = [
    "SubstrateInstance",
    "FundingLiquidityRolloverSubstrate",
    "CrossExposureContagionProxySubstrate",
    "VolatilityCreditSpreadRegimeSubstrate",
]
