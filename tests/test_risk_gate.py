"""Tests for CoherenceRiskGate middleware."""

from __future__ import annotations

from coherence_bridge.mock_engine import MockEngine
from coherence_bridge.risk_gate import CoherenceRiskGate, UnsafeCoherenceRiskGateHarness


def test_unknown_instrument_blocked_fail_closed() -> None:
    gate = CoherenceRiskGate(MockEngine(), fail_closed=True)
    decision = gate.apply("NONEXISTENT", 1.0)
    assert not decision.allowed
    assert decision.adjusted_size == 0.0
    assert "fail-closed" in decision.reason


def test_adjusted_size_never_exceeds_intended() -> None:
    """Invariant: risk gate NEVER amplifies position size."""
    engine = MockEngine()
    gate = CoherenceRiskGate(engine)
    for _ in range(100):
        for inst in engine.instruments:
            d = gate.apply(inst, 1.0)
            assert (
                d.adjusted_size <= 1.0
            ), f"Gate amplified size: {d.adjusted_size} > 1.0 for {inst} regime={d.regime}"


def test_critical_regime_always_blocked() -> None:
    """CRITICAL = herding/crash precursor → always block."""
    # Force a signal check — we can't control mock regime,
    # but we can verify the logic via direct signal injection
    from unittest.mock import MagicMock

    mock_engine = MagicMock()
    # in-band signal so the INV-CBR1 contract passes and the CRITICAL regime
    # branch is what blocks (not the contract).
    mock_engine.get_signal.return_value = {
        "regime": "CRITICAL",
        "gamma": 1.05,
        "risk_scalar": 0.9,
        "order_parameter_R": 0.95,
    }
    gate_crit = CoherenceRiskGate(mock_engine)
    d = gate_crit.apply("EURUSD", 1.0)
    assert not d.allowed
    assert d.regime == "CRITICAL"
    assert "CRITICAL" in d.reason


def test_decoherent_regime_blocked() -> None:
    from unittest.mock import MagicMock

    mock_engine = MagicMock()
    # Complete, in-band signal (gamma drives risk; R in [0,1]) so the INV-CBR1
    # contract passes and the DECOHERENT regime branch is what blocks.
    mock_engine.get_signal.return_value = {
        "regime": "DECOHERENT",
        "gamma": 1.6,
        "order_parameter_R": 0.2,
        "risk_scalar": 0.1,
    }
    gate = CoherenceRiskGate(mock_engine)
    d = gate.apply("EURUSD", 1.0)
    assert not d.allowed
    assert "DECOHERENT" in d.reason


def test_metastable_high_risk_passes() -> None:
    from unittest.mock import MagicMock

    mock_engine = MagicMock()
    # gamma=0.95 ⇒ safe_risk_scalar = 1-|0.95-1| = 0.95 (≥ metastable threshold).
    mock_engine.get_signal.return_value = {
        "regime": "METASTABLE",
        "gamma": 0.95,
        "order_parameter_R": 0.5,
        "risk_scalar": 0.95,
    }
    gate = CoherenceRiskGate(mock_engine)
    d = gate.apply("EURUSD", 1.0)
    assert d.allowed
    assert d.adjusted_size > 0
    assert d.adjusted_size <= 1.0


def test_coherent_applies_size_reduction() -> None:
    from unittest.mock import MagicMock

    mock_engine = MagicMock()
    # gamma=1.2 ⇒ safe_risk_scalar = 1-|1.2-1| = 0.8 (≥ coherent threshold).
    mock_engine.get_signal.return_value = {
        "regime": "COHERENT",
        "gamma": 1.2,
        "order_parameter_R": 0.5,
        "risk_scalar": 0.8,
    }
    gate = CoherenceRiskGate(mock_engine, coherent_size_factor=0.6)
    d = gate.apply("EURUSD", 1.0)
    assert d.allowed
    # 1.0 * 0.8 * 0.6 = 0.48
    assert abs(d.adjusted_size - 0.48) < 0.01


def test_gate_decision_fields() -> None:
    gate = CoherenceRiskGate(MockEngine())
    d = gate.apply("EURUSD", 1.0)
    # All fields present
    assert isinstance(d.allowed, bool)
    assert isinstance(d.adjusted_size, float)
    assert isinstance(d.reason, str)
    assert isinstance(d.regime, str)
    assert isinstance(d.risk_scalar, float)


# ── INV-CBR1 RUNTIME ENFORCEMENT at the real consumer (not just the unit gate) ──
# These prove the physics contract is wired into CoherenceRiskGate.apply: an
# out-of-band signal is HARD-BLOCKED by the order-sizing consumer itself.


def _gate_with_signal(sig: dict[str, object]) -> CoherenceRiskGate:
    from unittest.mock import MagicMock

    eng = MagicMock()
    eng.get_signal.return_value = sig
    return CoherenceRiskGate(eng)


def _otherwise_passing(**overrides: object) -> dict[str, object]:
    """A METASTABLE signal that WOULD pass — overrides poison one physics field."""
    sig: dict[str, object] = {
        "regime": "METASTABLE",
        "gamma": 1.0,
        "order_parameter_R": 0.5,
        "ollivier_kappa": 0.1,
        "risk_scalar": 1.0,
    }
    sig.update(overrides)
    return sig


def test_consumer_refuses_negative_gamma() -> None:
    """Negative out-of-band gamma is refused by the CONSUMER, not just the gate."""
    d = _gate_with_signal(_otherwise_passing(gamma=-0.5)).apply("EURUSD", 1.0)
    assert not d.allowed
    assert d.adjusted_size == 0.0
    assert "INVALID_PHYSICS_CONTRACT" in d.reason
    assert d.risk_scalar == 0.0


def test_consumer_refuses_ollivier_above_one() -> None:
    """Ollivier κ > 1 (INV-RC1) is refused by the consumer."""
    d = _gate_with_signal(_otherwise_passing(ollivier_kappa=1.5)).apply("EURUSD", 1.0)
    assert not d.allowed
    assert d.adjusted_size == 0.0
    assert "INV-RC1" in d.reason


def test_consumer_refuses_non_finite_R() -> None:
    """Non-finite / out-of-band R (INV-K1) is refused by the consumer."""
    d = _gate_with_signal(_otherwise_passing(order_parameter_R=float("nan"))).apply("EURUSD", 1.0)
    assert not d.allowed
    assert d.adjusted_size == 0.0
    assert "INV-K1" in d.reason


def test_consumer_uses_verdict_risk_not_raw() -> None:
    """Sizing uses the contract's safe_risk_scalar (from gamma), NOT raw risk_scalar.

    The raw field is poisoned high (0.99) while gamma=1.4 ⇒ safe risk = 0.6.
    A consumer that trusted the raw field would size on 0.99; the wired consumer
    sizes on the verdict's 0.6.
    """
    sig = _otherwise_passing(gamma=1.4, risk_scalar=0.99, regime="COHERENT")
    d = _gate_with_signal(sig).apply("EURUSD", 1.0)
    # COHERENT: size = 1 * safe_risk(0.6) * coherent_factor(0.6) = 0.36, not 0.99-driven.
    assert d.allowed
    assert abs(d.risk_scalar - 0.6) < 1e-6
    assert abs(d.adjusted_size - 0.36) < 0.01


def test_decision_surface_never_reads_raw_signal_risk_scalar() -> None:
    """Enforce-by-construction: the order-sizing decision surface must derive risk
    from the physics-contract verdict, never from the relayed raw signal field.

    Guards against a regression that re-introduces ``sig["risk_scalar"]`` /
    ``sig.get("risk_scalar")`` into the consumer's decision path (the raw field is
    advisory telemetry only; the authoritative value is verdict.safe_risk_scalar).
    """
    import pathlib
    import re

    src = pathlib.Path("coherence_bridge/risk_gate.py").read_text(encoding="utf-8")
    raw_reads = re.findall(r"""(?:sig|signal)(?:\.get\(\s*["']risk_scalar["']|\[\s*["']risk_scalar["']\])""", src)
    assert raw_reads == [], f"decision surface reads raw signal risk_scalar: {raw_reads}"


# ── Production fail-open is forbidden by construction (Task 2) ────────────────


def test_production_fail_open_is_rejected_at_construction() -> None:
    """fail_closed=False without the test env flag raises RuntimeError."""
    import os

    import pytest

    os.environ.pop(CoherenceRiskGate.FAIL_OPEN_TEST_ENV, None)
    with pytest.raises(RuntimeError, match="fail-open"):
        CoherenceRiskGate(MockEngine(), fail_closed=False)


def test_fail_open_only_via_unsafe_harness() -> None:
    """The fail-open branch is reachable ONLY through the loud test harness:
    a missing signal returns allowed=True (fail-open) inside the harness."""
    from unittest.mock import MagicMock

    eng = MagicMock()
    eng.get_signal.return_value = None
    with UnsafeCoherenceRiskGateHarness(eng) as gate:
        assert gate.fail_closed is False
        d = gate.apply("EURUSD", 1.0)
    assert d.allowed is True
    assert "fail-open" in d.reason


def test_harness_restores_env_flag() -> None:
    """The harness restores the env flag, so fail-open does not leak."""
    import os

    os.environ.pop(CoherenceRiskGate.FAIL_OPEN_TEST_ENV, None)
    with UnsafeCoherenceRiskGateHarness(MockEngine()):
        pass
    assert CoherenceRiskGate.FAIL_OPEN_TEST_ENV not in os.environ


def test_no_production_path_instantiates_fail_open() -> None:
    """grep-gate: no production CONSUMER module enables fail-open.

    risk_gate.py is the home of CoherenceRiskGate AND the sanctioned test-only
    UnsafeCoherenceRiskGateHarness (the single allowed fail_closed=False), so it
    is excluded; every OTHER coherence_bridge module must not construct a
    fail-open gate.
    """
    import pathlib

    offenders: list[str] = []
    for path in pathlib.Path("coherence_bridge").rglob("*.py"):
        if "test" in path.name or path.name == "risk_gate.py":
            continue
        if "fail_closed=False" in path.read_text(encoding="utf-8"):
            offenders.append(str(path))
    assert offenders == [], f"production consumer enables fail-open: {offenders}"
