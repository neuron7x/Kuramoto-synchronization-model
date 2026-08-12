# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Typed signal boundary (Task 5): the decision surface is typed, not a raw dict.

BridgeSignal / ValidatedBridgeSignal expose only safe decision fields; the raw
risk_scalar lives in telemetry. An import-lint guard keeps risk-from-gamma out of
the order-sizing decision surface (only the physics contract computes it).
"""

from __future__ import annotations

import pathlib

from coherence_bridge.physics_contract import (
    BridgeSignal,
    PhysicsContractStatus,
    ValidatedBridgeSignal,
)


def _in_band() -> dict[str, object]:
    return {
        "gamma": 1.0,
        "order_parameter_R": 0.5,
        "augmented_forman_ricci": 5.0,
        "ollivier_kappa": 0.1,
        "risk_scalar": 0.99,  # poisoned raw value
        "regime": "METASTABLE",
    }


def test_raw_risk_is_not_on_typed_decision_surface() -> None:
    sig = BridgeSignal.from_relayed(_in_band())
    assert not hasattr(sig, "risk_scalar")  # no raw field on the typed boundary
    assert sig.telemetry["raw_risk_scalar"] == 0.99  # raw lives only in telemetry
    assert "risk_scalar" not in sig.to_contract_dict()  # contract never sees raw


def test_validated_signal_carries_verdict_and_safe_risk() -> None:
    v = ValidatedBridgeSignal.of(BridgeSignal.from_relayed(_in_band()))
    assert v.verdict.status is PhysicsContractStatus.VALID
    assert not hasattr(v, "risk_scalar")
    # safe risk is derived from gamma by the contract (1.0 → 1.0), not the raw 0.99.
    assert abs(v.safe_risk_scalar - 1.0) < 1e-9
    assert v.regime == "METASTABLE"


def test_validated_signal_fails_closed_on_negative_gamma() -> None:
    bad = _in_band()
    bad["gamma"] = -0.5
    v = ValidatedBridgeSignal.of(BridgeSignal.from_relayed(bad))
    assert v.verdict.status is PhysicsContractStatus.INVALID_PHYSICS_CONTRACT
    assert v.safe_risk_scalar == 0.0


def test_forman_blend_above_one_does_not_invalidate() -> None:
    v = ValidatedBridgeSignal.of(BridgeSignal.from_relayed(_in_band()))  # forman=5.0
    assert v.verdict.is_valid  # Forman >1 is legitimate (not the κ-bound field)


def test_decision_surface_does_not_compute_risk_from_gamma() -> None:
    """import-lint: the order-sizing surface (risk_gate.py) must not call
    compute_risk_scalar or compute risk from gamma — it uses the verdict."""
    src = pathlib.Path("coherence_bridge/risk_gate.py").read_text(encoding="utf-8")
    assert "compute_risk_scalar" not in src
    assert "abs(gamma" not in src
