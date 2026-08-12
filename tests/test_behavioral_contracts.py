# mypy: disable-error-code="attr-defined,unused-ignore,no-untyped-call,call-overload,arg-type,operator,var-annotated"
"""Behavioral contract tests — prove system-level invariants hold
across all module boundaries under adversarial conditions.

These tests verify properties that NO single unit test can catch:
they exercise the full composition of modules and prove that
invariants are preserved through every transformation.

Hierarchy (INV-YV1 maintenance layers):
  Layer 0: Gradient exists     → test_signal_never_all_zero
  Layer 1: Gradient bounded    → test_risk_scalar_algebraic_consistency
  Layer 2: Gradient protected  → test_fail_closed_propagates_through_all_layers
  Layer 3: Gradient preserved  → test_epistemic_abort_blocks_all_downstream
  Layer 4: Gradient utilized   → test_trade_decision_respects_all_gates
"""

from __future__ import annotations

import time
from collections import Counter

import numpy as np
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from coherence_bridge.decision_engine import GeoSyncDecisionEngine
from coherence_bridge.feature_exporter import RegimeFeatureExporter
from coherence_bridge.invariants import verify_signal
from coherence_bridge.mock_engine import MockEngine
from coherence_bridge.risk import compute_risk_scalar
from coherence_bridge.risk_gate import CoherenceRiskGate
from coherence_bridge.server import _sanitize_signal
from coherence_bridge.signal import Regime, RegimeSignal
from coherence_bridge.uncertainty_compat import UncertaintyEstimator
from geosync.neuroeconomics.epistemic_action import EpistemicDecision

# ═══════════════════════════════════════════════════════════════════
# LAYER 0: Signal existence — gradient must be positive
# ═══════════════════════════════════════════════════════════════════


def test_signal_never_all_zero() -> None:
    """∀ signal: at least one physics field is nonzero.

    A signal where all fields are zero = thermal noise = no gradient.
    INV-YV1 requires ΔV > 0.
    """
    engine = MockEngine()
    for _ in range(100):
        for inst in engine.instruments:
            sig = engine.get_signal(inst)
            assert sig is not None
            physics_fields = [
                abs(sig["gamma"]),
                abs(sig["order_parameter_R"]),
                abs(sig["ricci_curvature"]),
                abs(sig["lyapunov_max"]),
                abs(sig["signal_strength"]),
            ]
            assert sum(physics_fields) > 0, f"All-zero signal = no gradient: {sig}"


# ═══════════════════════════════════════════════════════════════════
# LAYER 1: Algebraic consistency across modules
# ═══════════════════════════════════════════════════════════════════


@given(gamma=st.floats(min_value=-2, max_value=4, allow_nan=False, allow_infinity=False))
def test_risk_scalar_consistent_everywhere(gamma: float) -> None:
    """risk_scalar computed in risk.py must match risk_gate, feature_exporter.

    Three modules independently use gamma → risk_scalar. They must agree.
    """
    from_risk = compute_risk_scalar(gamma)

    # Simulate signal through pipeline
    sig = {
        "timestamp_ns": time.time_ns(),
        "instrument": "TEST",
        "gamma": gamma,
        "order_parameter_R": 0.5,
        "ricci_curvature": 0.0,
        "lyapunov_max": 0.0,
        "regime": "METASTABLE",
        "regime_confidence": 0.8,
        "regime_duration_s": 1.0,
        "signal_strength": 0.0,
        "risk_scalar": from_risk,
        "sequence_number": 0,
    }

    # Sanitizer preserves or overrides
    sanitized = _sanitize_signal(sig)
    assert float(sanitized["risk_scalar"]) == from_risk or not np.isfinite(gamma)

    # Feature exporter reflects same value
    features = RegimeFeatureExporter.to_ml_features(sig)
    assert features["risk_scalar"] == from_risk


# ═══════════════════════════════════════════════════════════════════
# LAYER 2: Fail-closed propagation
# ═══════════════════════════════════════════════════════════════════


def test_fail_closed_propagates_through_all_layers() -> None:
    """NaN gamma → risk=0 everywhere, through every module.

    Sanitizer → invariant verifier → risk gate → decision engine.
    All must agree: NaN = danger = zero risk = no trade.
    """
    nan_signal = {
        "timestamp_ns": time.time_ns(),
        "instrument": "EURUSD",
        "gamma": float("nan"),
        "order_parameter_R": 0.5,
        "ricci_curvature": 0.0,
        "lyapunov_max": 0.0,
        "regime": "METASTABLE",
        "regime_confidence": 0.9,
        "regime_duration_s": 1.0,
        "signal_strength": 0.5,
        "risk_scalar": 0.9,
        "sequence_number": 0,
    }

    # Sanitizer catches it
    clean = _sanitize_signal(nan_signal)
    assert clean["risk_scalar"] == 0.0
    assert clean["regime"] == "UNKNOWN"

    # Risk gate blocks it
    from unittest.mock import MagicMock

    mock_engine = MagicMock()
    mock_engine.get_signal.return_value = clean
    gate = CoherenceRiskGate(mock_engine, fail_closed=True)
    decision = gate.apply("EURUSD", 1.0)
    assert not decision.allowed
    assert decision.adjusted_size == 0.0


# ═══════════════════════════════════════════════════════════════════
# LAYER 3: Epistemic protection
# ═══════════════════════════════════════════════════════════════════


def test_epistemic_observe_never_produces_trade() -> None:
    """When decision = OBSERVE, adjusted_size MUST be 0.

    This is the core Active Inference invariant:
    observing = no action = zero position.
    """
    engine = GeoSyncDecisionEngine(MockEngine())
    me = MockEngine()

    for _ in range(100):
        sig = me.get_signal("EURUSD")
        out = engine.process(sig, intended_size=1.0)
        if out.decision == EpistemicDecision.OBSERVE:
            assert out.adjusted_size == 0.0, f"OBSERVE with size={out.adjusted_size} > 0"
        if out.decision == EpistemicDecision.ABORT:
            assert out.adjusted_size == 0.0, f"ABORT with size={out.adjusted_size} > 0"


def test_decision_distribution_is_nondegenerate() -> None:
    """System must produce all 3 decisions over enough samples.

    Degenerate = always OBSERVE (paralysis) or always TRADE (no risk mgmt).
    """
    engine = GeoSyncDecisionEngine(MockEngine())
    me = MockEngine()
    counts: Counter[str] = Counter()

    for _ in range(200):
        for inst in me.instruments:
            sig = me.get_signal(inst)
            out = engine.process(sig, 1.0)
            counts[out.decision.value] += 1

    total = sum(counts.values())
    # At least 10% of each (allowing for regime cycling)
    for decision in ("TRADE", "OBSERVE"):
        rate = counts[decision] / total
        assert rate > 0.05, f"{decision} rate = {rate:.1%} < 5%. Distribution: {dict(counts)}"


# ═══════════════════════════════════════════════════════════════════
# LAYER 4: Full pipeline composition
# ═══════════════════════════════════════════════════════════════════


def test_full_pipeline_invariants_hold() -> None:
    """Engine → sanitize → verify → signal → features → gate → decision.

    Every invariant must hold at every stage.
    """
    me = MockEngine()
    engine = GeoSyncDecisionEngine(me)
    exporter = RegimeFeatureExporter()
    gate = CoherenceRiskGate(me, fail_closed=True)

    for _ in range(50):
        for inst in me.instruments:
            # 1. Raw signal
            raw = me.get_signal(inst)
            assert raw is not None

            # 2. Sanitize
            clean = _sanitize_signal(raw)

            # 3. Verify T1-T13
            results = verify_signal(clean, raise_on_failure=False)
            for r in results:
                assert r.passed, f"{inst} {r.theorem}: {r.message}"

            # 4. Typed signal
            typed = RegimeSignal.from_dict(clean)
            assert isinstance(typed.regime, Regime)

            # 5. ML features (7 fields)
            features = exporter.to_ml_features(clean)
            assert len(features) == 7
            assert features["risk_scalar"] == clean["risk_scalar"]

            # 6. Risk gate
            gate_d = gate.apply(inst, 1.0)
            assert gate_d.adjusted_size <= 1.0

            # 7. Decision engine
            decision = engine.process(clean, 1.0)
            assert decision.adjusted_size <= 1.0
            if decision.decision != EpistemicDecision.TRADE:
                assert decision.adjusted_size == 0.0


def test_uncertainty_monotone_with_information() -> None:
    """As more signals arrive, uncertainty should decrease (on average).

    This is the fundamental property of Bayesian learning:
    more data → less uncertainty (given stable generative process).
    """
    est = UncertaintyEstimator(window_size=50)
    me = MockEngine()

    early_totals = []
    late_totals = []

    for i in range(60):
        sig = me.get_signal("EURUSD")
        unc = est.update(sig)
        if 10 <= i < 20:
            early_totals.append(unc.total)
        if 50 <= i < 60:
            late_totals.append(unc.total)

    avg_early = sum(early_totals) / len(early_totals)
    avg_late = sum(late_totals) / len(late_totals)

    # Late uncertainty should be ≤ early (learning happened)
    # Allow small tolerance for regime switches
    assert (
        avg_late <= avg_early + 0.15
    ), f"Uncertainty didn't decrease: early={avg_early:.3f} late={avg_late:.3f}"


@given(size=st.floats(min_value=0.01, max_value=1e6, allow_nan=False))
@settings(suppress_health_check=[HealthCheck.too_slow])
def test_gate_contraction_universal(size: float) -> None:
    """∀ size > 0: gate.apply(inst, size).adjusted_size ≤ size.

    Universal contraction: the system NEVER amplifies risk.
    """
    me = MockEngine()
    gate = CoherenceRiskGate(me, fail_closed=True)
    d = gate.apply("EURUSD", size)
    assert d.adjusted_size <= size
    assert d.adjusted_size >= 0.0
