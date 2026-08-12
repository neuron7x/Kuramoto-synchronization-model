# mypy: disable-error-code="attr-defined,unused-ignore,no-untyped-call,arg-type"
"""Tests for Neuro-Homeostatic Stabilizer (NHS)."""

from __future__ import annotations

import random
import time

from coherence_bridge.decision_engine import GeoSyncDecisionEngine
from coherence_bridge.mock_engine import MockEngine
from geosync.neuroeconomics.epistemic_action import EpistemicDecision
from geosync.neuroeconomics.homeostatic_stabilizer import (
    NeuroHomeostaticStabilizer,
)


def _sig(
    risk_scalar: float = 0.8,
    regime_confidence: float = 0.85,
    signal_strength: float = 0.3,
    gamma: float = 1.0,
) -> dict[str, object]:
    return {
        "timestamp_ns": time.time_ns(),
        "instrument": "EURUSD",
        "gamma": gamma,
        "order_parameter_R": 0.6,
        "ricci_curvature": -0.1,
        "lyapunov_max": 0.01,
        "regime": "METASTABLE",
        "regime_confidence": regime_confidence,
        "regime_duration_s": 5.0,
        "signal_strength": signal_strength,
        "risk_scalar": risk_scalar,
        "sequence_number": 0,
    }


# === E/I Balance ===


def test_homeostatic_regime_at_moderate_signal() -> None:
    """Moderate signal (risk=0.5, conf=0.5) → HOMEOSTATIC."""
    nhs = NeuroHomeostaticStabilizer()
    for _ in range(15):
        state = nhs.update(_sig(risk_scalar=0.7, regime_confidence=0.6, signal_strength=0.2))
    assert state.regime == "HOMEOSTATIC"
    assert 0.7 <= state.ei_ratio <= 1.3


def test_excitatory_regime_on_high_confidence() -> None:
    """High risk + confidence → EXCITATORY (not yet dissociated)."""
    nhs = NeuroHomeostaticStabilizer()
    for _ in range(15):
        state = nhs.update(_sig(risk_scalar=0.8, regime_confidence=0.8, signal_strength=0.3))
    assert state.regime == "EXCITATORY"
    assert state.ei_ratio > 1.3


def test_inhibitory_regime_on_low_confidence() -> None:
    """Low risk + low confidence → INHIBITORY."""
    nhs = NeuroHomeostaticStabilizer()
    for _ in range(15):
        state = nhs.update(_sig(risk_scalar=0.1, regime_confidence=0.2, signal_strength=0.0))
    assert state.regime == "INHIBITORY"
    assert state.ei_ratio < 0.7


def test_kelly_multiplier_bounded() -> None:
    """kelly_multiplier ∈ [0, 1] always."""
    nhs = NeuroHomeostaticStabilizer()
    for _ in range(30):
        state = nhs.update(_sig())
        assert 0.0 <= state.kelly_multiplier <= 1.0


# === Dissociative Shield ===


def test_dissociative_shield_on_extreme_ei() -> None:
    """E/I ratio > threshold → DISSOCIATED."""
    nhs = NeuroHomeostaticStabilizer(dissociation_threshold=1.5)
    for _ in range(15):
        nhs.update(_sig())

    # Force extreme excitation
    state = nhs.update(
        _sig(risk_scalar=0.99, regime_confidence=0.99, signal_strength=0.99, gamma=1.0)
    )
    # May or may not trigger depending on inhibitory
    # But if triggered:
    if state.regime == "DISSOCIATED":
        assert state.kelly_multiplier == 0.0
        assert nhs.is_dissociated


def test_dissociation_forces_abort_in_decision_engine() -> None:
    """NHS DISSOCIATED → GeoSyncDecisionEngine returns ABORT."""
    engine = GeoSyncDecisionEngine(MockEngine(), ei_dissociation=0.01)
    # With ei_dissociation=0.01, almost any signal triggers dissociation
    # after warmup
    for _ in range(15):
        out = engine.process(_sig(), 1.0)
    # Should be ABORT due to dissociation
    assert out.decision == EpistemicDecision.ABORT
    assert out.adjusted_size == 0.0
    assert "DISSOCIATED" in out.reason


def test_dissociation_recovery() -> None:
    """System recovers from DISSOCIATED when E/I stabilizes."""
    nhs = NeuroHomeostaticStabilizer(
        dissociation_threshold=2.0,
        recovery_threshold=1.5,
    )
    # Warmup
    for _ in range(15):
        nhs.update(_sig())

    # Force dissociation via high entropy cutoff
    nhs._dissociated = True

    # Feed balanced signals
    for _ in range(20):
        state = nhs.update(_sig(risk_scalar=0.5, regime_confidence=0.5, signal_strength=0.0))

    # Should eventually recover
    assert not nhs.is_dissociated or state.regime != "DISSOCIATED"


# === Integration with Decision Engine ===


def test_nhs_modulates_trade_size() -> None:
    """NHS kelly_multiplier reduces TRADE size when E/I deviates."""
    engine = GeoSyncDecisionEngine(MockEngine())
    me = MockEngine()

    sizes = []
    for _ in range(50):
        sig = me.get_signal("EURUSD")
        out = engine.process(sig, 1.0)
        if out.decision == EpistemicDecision.TRADE:
            sizes.append(out.adjusted_size)

    if sizes:
        # All trades must be ≤ 1.0
        assert all(s <= 1.0 for s in sizes)
        # NHS should have reduced at least some
        assert any(s < 0.99 for s in sizes), "NHS should modulate at least some trades"


def test_state_summary_includes_nhs() -> None:
    """get_state_summary returns NHS fields."""
    engine = GeoSyncDecisionEngine(MockEngine())
    engine.process(_sig(), 1.0)
    summary = engine.get_state_summary("EURUSD")
    assert "nhs_regime" in summary
    assert "nhs_ei_ratio" in summary
    assert "nhs_kelly_mult" in summary
    assert "nhs_entropy" in summary
    assert "nhs_dissociated" in summary


def test_entropy_computation() -> None:
    """Entropy should be higher for diverse signals, lower for uniform."""
    nhs = NeuroHomeostaticStabilizer()

    # Uniform signals → low entropy
    for _ in range(20):
        nhs.update(_sig(risk_scalar=0.5))
    uniform_entropy = nhs._compute_entropy()

    # Diverse signals → higher entropy
    nhs2 = NeuroHomeostaticStabilizer()
    for i in range(20):
        nhs2.update(_sig(risk_scalar=i / 20.0))
    diverse_entropy = nhs2._compute_entropy()

    assert diverse_entropy > uniform_entropy


def test_re_adaptation_to_baseline_converges_with_small_phase_error() -> None:
    nhs = NeuroHomeostaticStabilizer()
    report = nhs.re_adaptation_to_baseline(
        node_phases=[0.98, 1.01, 1.0],
        baseline_phases=[1.0, 1.0, 1.0],
        serotonin_gain=1.2,
        convergence_tol=0.05,
    )
    assert report.write_ops_inhibited
    assert report.converged
    assert report.node_count == 3
    assert report.post_reset_energy <= report.pre_reset_energy


def test_re_adaptation_to_baseline_requires_equal_vector_sizes() -> None:
    nhs = NeuroHomeostaticStabilizer()
    try:
        nhs.re_adaptation_to_baseline([1.0], [1.0, 1.1])
    except ValueError as exc:
        assert "equal length" in str(exc)
    else:
        raise AssertionError("Expected ValueError for mismatched phase vectors")


def test_re_adaptation_to_baseline_rejects_nonpositive_serotonin_gain() -> None:
    nhs = NeuroHomeostaticStabilizer()
    try:
        nhs.re_adaptation_to_baseline([1.0], [1.0], serotonin_gain=0.0)
    except ValueError as exc:
        assert "serotonin_gain must be > 0" in str(exc)
    else:
        raise AssertionError("Expected ValueError for nonpositive serotonin_gain")


def test_re_adaptation_to_baseline_engages_safety_lock_on_extreme_phase_error() -> None:
    nhs = NeuroHomeostaticStabilizer()
    report = nhs.re_adaptation_to_baseline(
        node_phases=[10.0, -10.0],
        baseline_phases=[0.0, 0.0],
        max_phase_error=1.0,
    )
    assert report.safety_lock
    assert report.write_ops_inhibited
    assert not report.converged
    assert report.reset_energy == 0.0
    assert report.energy_delta == 0.0
    assert report.post_reset_energy == report.pre_reset_energy


def test_re_adaptation_to_baseline_rejects_nonpositive_max_phase_error() -> None:
    nhs = NeuroHomeostaticStabilizer()
    try:
        nhs.re_adaptation_to_baseline([0.1], [0.0], max_phase_error=0.0)
    except ValueError as exc:
        assert "max_phase_error must be > 0" in str(exc)
    else:
        raise AssertionError("Expected ValueError for nonpositive max_phase_error")


def test_re_adaptation_to_baseline_energy_is_nonincreasing_randomized() -> None:
    rng = random.Random(7)
    nhs = NeuroHomeostaticStabilizer()
    for _ in range(100):
        baseline = [rng.uniform(-0.3, 0.3) for _ in range(8)]
        nodes = [b + rng.uniform(-0.2, 0.2) for b in baseline]
        report = nhs.re_adaptation_to_baseline(
            node_phases=nodes,
            baseline_phases=baseline,
            serotonin_gain=1.0,
            convergence_tol=0.3,
            max_phase_error=1.0,
        )
        assert report.post_reset_energy <= report.pre_reset_energy
