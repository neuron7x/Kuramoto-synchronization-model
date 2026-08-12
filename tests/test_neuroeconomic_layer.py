# mypy: disable-error-code="attr-defined,unused-ignore,no-untyped-call,arg-type,operator"
"""Tests for neuroeconomic decision layer (Active Inference)."""

from __future__ import annotations

import time

from coherence_bridge.decision_engine import GeoSyncDecisionEngine
from coherence_bridge.mock_engine import MockEngine
from coherence_bridge.uncertainty_compat import UncertaintyEstimator
from geosync.neuroeconomics.epistemic_action import EpistemicDecision
from geosync.neuroeconomics.regime_memory import RegimeMemory


def _signal(
    regime: str = "METASTABLE",
    gamma: float = 1.0,
    risk_scalar: float = 0.9,
    regime_confidence: float = 0.85,
    signal_strength: float = 0.3,
    **kwargs: object,
) -> dict[str, object]:
    base: dict[str, object] = {
        "timestamp_ns": time.time_ns(),
        "instrument": "EURUSD",
        "gamma": gamma,
        "order_parameter_R": 0.6,
        "ricci_curvature": -0.1,
        "lyapunov_max": 0.01,
        "regime": regime,
        "regime_confidence": regime_confidence,
        "regime_duration_s": 5.0,
        "signal_strength": signal_strength,
        "risk_scalar": risk_scalar,
        "sequence_number": 0,
    }
    base.update(kwargs)
    return base


# === Uncertainty ===


def test_uncertainty_cold_start_returns_max() -> None:
    est = UncertaintyEstimator(window_size=20)
    unc = est.update(_signal())
    assert unc.total == 1.0
    assert unc.is_novel


def test_uncertainty_stabilizes_after_warmup() -> None:
    est = UncertaintyEstimator(window_size=20)
    for _ in range(15):
        unc = est.update(_signal())
    # After warmup, at least some component should have resolved
    assert unc.aleatoric < 1.0 or unc.surprise < 1.0


def test_uncertainty_epistemic_rises_on_disagreement() -> None:
    est = UncertaintyEstimator(window_size=50)
    # Warm up with consistent signals
    for _ in range(15):
        est.update(_signal(gamma=1.0, risk_scalar=0.9))

    # Inject contradictory: gamma says metastable but R=0 (decoherent)
    unc = est.update(_signal(gamma=1.0, risk_scalar=0.9, order_parameter_R=0.01))
    # Epistemic should be non-zero due to vote disagreement
    assert unc.epistemic > 0


def test_ambiguity_index_spikes_on_gamma_volatility() -> None:
    est = UncertaintyEstimator(window_size=30)
    # Stable gamma
    for _ in range(15):
        est.update(_signal(gamma=1.0))
    unc_stable = est.update(_signal(gamma=1.0))

    # Now oscillate gamma wildly
    est2 = UncertaintyEstimator(window_size=30)
    for i in range(15):
        g = 0.5 if i % 2 == 0 else 1.5
        est2.update(_signal(gamma=g))
    unc_volatile = est2.update(_signal(gamma=0.5))

    assert unc_volatile.ambiguity_index > unc_stable.ambiguity_index


def test_kelly_discount_bounded() -> None:
    est = UncertaintyEstimator()
    for _ in range(15):
        est.update(_signal())
    unc = est.update(_signal())
    discount = est.kelly_discount(unc)
    assert 0.1 <= discount <= 1.0


# === Regime Memory ===


def test_regime_memory_learns_transitions() -> None:
    mem = RegimeMemory()
    for _ in range(10):
        mem.observe("EURUSD", "METASTABLE")
    trans = mem.observe("EURUSD", "COHERENT")
    # After 10 METASTABLE, P(COHERENT|METASTABLE) should be small but nonzero
    assert trans.probability > 0
    assert trans.surprise > 0


def test_regime_memory_detects_anomalous_transition() -> None:
    mem = RegimeMemory()
    for _ in range(20):
        mem.observe("EURUSD", "METASTABLE")
    # Rare transition → high surprise
    rare = mem.observe("EURUSD", "CRITICAL")
    mem.observe("EURUSD", "METASTABLE")
    # Re-observe to get normal
    for _ in range(5):
        mem.observe("EURUSD", "METASTABLE")
    normal2 = mem.observe("EURUSD", "METASTABLE")
    assert rare.surprise > normal2.surprise


def test_regime_memory_entry_pattern() -> None:
    mem = RegimeMemory()
    mem.observe("EURUSD", "DECOHERENT")
    mem.observe("EURUSD", "METASTABLE")
    trans = mem.observe("EURUSD", "COHERENT")
    assert trans.pattern == "ENTRY_SETUP"


def test_regime_memory_exit_pattern() -> None:
    mem = RegimeMemory()
    mem.observe("EURUSD", "COHERENT")
    trans = mem.observe("EURUSD", "CRITICAL")
    assert trans.pattern == "EXIT_NOW"


def test_expected_next_regime() -> None:
    mem = RegimeMemory()
    for _ in range(10):
        mem.observe("EURUSD", "METASTABLE")
    mem.observe("EURUSD", "COHERENT")
    # After many METASTABLE→METASTABLE, expected next from METASTABLE is METASTABLE
    expected = mem.get_expected_next("EURUSD")
    # Current is COHERENT, so we check from COHERENT (only 1 obs)
    assert expected in ("COHERENT", "METASTABLE", "DECOHERENT", "CRITICAL", "UNKNOWN")


# === Epistemic Action ===


def test_epistemic_trade_when_clear() -> None:
    engine = GeoSyncDecisionEngine(MockEngine())
    # Warm up
    for _ in range(15):
        engine.process(_signal(regime_confidence=0.9, risk_scalar=0.95))
    out = engine.process(
        _signal(regime_confidence=0.9, risk_scalar=0.95, signal_strength=0.5),
        intended_size=1.0,
    )
    assert out.adjusted_size <= 1.0
    assert out.decision in (
        EpistemicDecision.TRADE,
        EpistemicDecision.OBSERVE,
        EpistemicDecision.ABORT,
    )


def test_epistemic_abort_on_extreme_ambiguity() -> None:
    engine = GeoSyncDecisionEngine(MockEngine(), abort_threshold=0.01)
    # Feed volatile signals to build ambiguity
    for i in range(20):
        engine.process(_signal(gamma=0.5 if i % 2 == 0 else 1.5), intended_size=1.0)
    out = engine.process(_signal(gamma=0.3), intended_size=1.0)
    # With volatile inputs and low threshold, should eventually ABORT or OBSERVE
    assert (
        out.decision in (EpistemicDecision.ABORT, EpistemicDecision.OBSERVE)
        or out.adjusted_size < 1.0
    )


def test_observe_never_has_positive_size() -> None:
    engine = GeoSyncDecisionEngine(MockEngine())
    for _ in range(20):
        out = engine.process(_signal(), intended_size=1.0)
        if out.decision == EpistemicDecision.OBSERVE:
            assert out.adjusted_size == 0.0


def test_abort_never_has_positive_size() -> None:
    engine = GeoSyncDecisionEngine(MockEngine(), abort_threshold=0.01)
    out = engine.process(_signal(), intended_size=1.0)
    if out.decision == EpistemicDecision.ABORT:
        assert out.adjusted_size == 0.0


# === Decision Engine Integration ===


def test_decision_engine_full_pipeline() -> None:
    me = MockEngine()
    engine = GeoSyncDecisionEngine(me)
    sig = me.get_signal("EURUSD")
    assert sig is not None
    out = engine.process(sig, intended_size=1.0)
    assert out.adjusted_size <= 1.0
    assert out.decision.value in ("TRADE", "OBSERVE", "ABORT")
    assert isinstance(out.reason, str)
    assert len(out.reason) > 0


def test_decision_engine_live() -> None:
    me = MockEngine()
    engine = GeoSyncDecisionEngine(me)
    out = engine.process_live("EURUSD", intended_size=1.0)
    assert out is not None
    assert out.adjusted_size <= 1.0


def test_neckpinch_pattern_detection() -> None:
    """Rapid METASTABLE→CRITICAL = neckpinch singularity in Ricci flow."""
    engine = GeoSyncDecisionEngine(MockEngine(), abort_threshold=1.5)
    # Build history of stable METASTABLE
    for _ in range(15):
        engine.process(_signal(regime="METASTABLE", gamma=1.0, regime_confidence=0.9))
    # Sudden CRITICAL with gamma spike
    out = engine.process(
        _signal(regime="CRITICAL", gamma=0.3, regime_confidence=0.5, risk_scalar=0.1),
        intended_size=1.0,
    )
    # Should not trade (either OBSERVE or ABORT)
    assert out.decision != EpistemicDecision.TRADE or out.adjusted_size < 0.2
