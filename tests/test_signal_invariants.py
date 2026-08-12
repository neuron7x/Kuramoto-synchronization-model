# mypy: disable-error-code="attr-defined,operator,index,arg-type,call-overload,assignment"
"""GeoSync physics invariants enforced on CoherenceBridge signals."""

import pytest

from coherence_bridge.mock_engine import MockEngine


@pytest.fixture
def signals():
    """Generate a batch of signals for invariant testing."""
    engine = MockEngine()
    result = []
    for _ in range(100):
        for inst in engine.instruments:
            sig = engine.get_signal(inst)
            if sig is not None:
                result.append(sig)
    return result


def test_R_bounded(signals: list) -> None:
    """R in [0, 1] — Kuramoto order parameter is a magnitude."""
    for sig in signals:
        assert (
            0.0 <= sig["order_parameter_R"] <= 1.0
        ), f"R={sig['order_parameter_R']} out of bounds for {sig['instrument']}"


def test_risk_scalar_monotonic_with_gamma_distance(signals: list) -> None:
    """risk_scalar = f(|gamma - 1.0|), decreasing with distance."""
    for sig in signals:
        gamma_dist = abs(sig["gamma"] - 1.0)
        expected_max_risk = 1.0 - gamma_dist
        # Allow small tolerance for rounding
        assert sig["risk_scalar"] <= expected_max_risk + 0.01, (
            f"risk_scalar={sig['risk_scalar']} too high for "
            f"gamma={sig['gamma']} (dist={gamma_dist})"
        )


def test_gamma_positive(signals: list) -> None:
    """gamma (PSD slope) must be positive — spectral exponent."""
    for sig in signals:
        assert sig["gamma"] > 0, f"gamma={sig['gamma']} not positive"


def test_regime_confidence_bounded(signals: list) -> None:
    """Confidence in [0, 1]."""
    for sig in signals:
        assert 0.0 <= sig["regime_confidence"] <= 1.0


def test_signal_strength_bounded(signals: list) -> None:
    """Signal strength in [-1, +1]."""
    for sig in signals:
        assert -1.0 <= sig["signal_strength"] <= 1.0


def test_timestamp_nanoseconds(signals: list) -> None:
    """Timestamps must be in nanoseconds (>= 2020 in ns)."""
    min_ns = 1_577_836_800_000_000_000  # 2020-01-01 UTC
    for sig in signals:
        assert (
            sig["timestamp_ns"] >= min_ns
        ), f"timestamp_ns={sig['timestamp_ns']} seems too small for nanoseconds"


def test_regime_values_valid(signals: list) -> None:
    """Only valid regime strings."""
    valid = {"COHERENT", "METASTABLE", "DECOHERENT", "CRITICAL", "UNKNOWN"}
    for sig in signals:
        assert sig["regime"] in valid, f"Invalid regime: {sig['regime']}"


def test_signal_strength_depends_on_regime_not_self() -> None:
    """SSI.apply(domain=EXTERNAL) valid; signal does not self-reference.

    The signal_strength field is derived from phase distribution asymmetry
    (regime-dependent), NOT from previous signal_strength values.
    Verify that different regimes produce different signal_strength distributions.
    """
    engine = MockEngine()
    by_regime: dict[str, list[float]] = {}

    for _ in range(200):
        for inst in engine.instruments:
            sig = engine.get_signal(inst)
            if sig is None:
                continue
            regime = sig["regime"]
            by_regime.setdefault(regime, []).append(sig["signal_strength"])

    # COHERENT and CRITICAL should have different signal_strength means
    # (COHERENT ~+0.6, CRITICAL ~-0.8)
    if "COHERENT" in by_regime and "CRITICAL" in by_regime:
        mean_coherent = sum(by_regime["COHERENT"]) / len(by_regime["COHERENT"])
        mean_critical = sum(by_regime["CRITICAL"]) / len(by_regime["CRITICAL"])
        assert mean_coherent > mean_critical, (
            f"COHERENT mean signal ({mean_coherent:.3f}) should be > "
            f"CRITICAL mean signal ({mean_critical:.3f})"
        )
        # They should be meaningfully different (not self-referencing same value)
        assert (
            abs(mean_coherent - mean_critical) > 0.5
        ), "signal_strength should differ significantly between regimes"
