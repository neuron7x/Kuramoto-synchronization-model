# mypy: disable-error-code="attr-defined,operator,index,arg-type,call-overload,assignment"
"""Mock engine: valid signals, regime value ranges, physics plausibility."""

import pytest

from coherence_bridge.mock_engine import MockEngine

REQUIRED_KEYS = {
    "timestamp_ns",
    "instrument",
    "gamma",
    "order_parameter_R",
    "ricci_curvature",
    "lyapunov_max",
    "regime",
    "regime_confidence",
    "regime_duration_s",
    "signal_strength",
    "risk_scalar",
    "sequence_number",
}

VALID_REGIMES = {"COHERENT", "METASTABLE", "DECOHERENT", "CRITICAL"}


@pytest.fixture
def engine():
    return MockEngine()


def test_instruments_not_empty(engine: MockEngine) -> None:
    assert len(engine.instruments) >= 3


def test_all_instruments_produce_signals(engine: MockEngine) -> None:
    for inst in engine.instruments:
        sig = engine.get_signal(inst)
        assert sig is not None
        assert sig["instrument"] == inst


def test_unknown_instrument_returns_none(engine: MockEngine) -> None:
    assert engine.get_signal("NONEXISTENT") is None


def test_signal_has_all_required_keys(engine: MockEngine) -> None:
    sig = engine.get_signal("EURUSD")
    assert sig is not None
    assert set(sig.keys()) == REQUIRED_KEYS


def test_value_ranges(engine: MockEngine) -> None:
    for _ in range(50):
        for inst in engine.instruments:
            sig = engine.get_signal(inst)
            assert sig is not None
            assert 0.0 <= sig["order_parameter_R"] <= 1.0
            assert 0.0 <= sig["risk_scalar"] <= 1.0
            assert 0.0 <= sig["regime_confidence"] <= 1.0
            assert -1.0 <= sig["signal_strength"] <= 1.0
            assert sig["regime"] in VALID_REGIMES
            assert sig["gamma"] > 0
            assert sig["timestamp_ns"] > 0


def test_regime_physics_plausibility(engine: MockEngine) -> None:
    """Each regime should produce characteristic value ranges."""
    # Collect signals by regime
    by_regime: dict[str, list[dict]] = {r: [] for r in VALID_REGIMES}
    for _ in range(200):
        for inst in engine.instruments:
            sig = engine.get_signal(inst)
            if sig is not None:
                by_regime[sig["regime"]].append(sig)

    # CRITICAL: high R (herding), positive Lyapunov (chaotic)
    if by_regime["CRITICAL"]:
        avg_R = sum(s["order_parameter_R"] for s in by_regime["CRITICAL"]) / len(
            by_regime["CRITICAL"]
        )
        avg_lyap = sum(s["lyapunov_max"] for s in by_regime["CRITICAL"]) / len(
            by_regime["CRITICAL"]
        )
        assert avg_R > 0.7, f"CRITICAL should have high R, got {avg_R}"
        assert avg_lyap > 0, f"CRITICAL should have positive Lyapunov, got {avg_lyap}"

    # DECOHERENT: low R, positive Lyapunov
    if by_regime["DECOHERENT"]:
        avg_R = sum(s["order_parameter_R"] for s in by_regime["DECOHERENT"]) / len(
            by_regime["DECOHERENT"]
        )
        assert avg_R < 0.4, f"DECOHERENT should have low R, got {avg_R}"

    # METASTABLE: gamma near 1.0
    if by_regime["METASTABLE"]:
        avg_gamma = sum(s["gamma"] for s in by_regime["METASTABLE"]) / len(by_regime["METASTABLE"])
        assert 0.8 < avg_gamma < 1.2, f"METASTABLE gamma should be ~1.0, got {avg_gamma}"

    # COHERENT: high R, negative Lyapunov (stable)
    if by_regime["COHERENT"]:
        avg_R = sum(s["order_parameter_R"] for s in by_regime["COHERENT"]) / len(
            by_regime["COHERENT"]
        )
        avg_lyap = sum(s["lyapunov_max"] for s in by_regime["COHERENT"]) / len(
            by_regime["COHERENT"]
        )
        assert avg_R > 0.6, f"COHERENT should have high R, got {avg_R}"
        assert avg_lyap < 0, f"COHERENT should have negative Lyapunov, got {avg_lyap}"


def test_sequence_number_monotonic(engine: MockEngine) -> None:
    """sequence_number must increase monotonically per instrument."""
    for inst in engine.instruments:
        prev = -1
        for _ in range(20):
            sig = engine.get_signal(inst)
            assert sig is not None
            assert sig["sequence_number"] > prev
            prev = sig["sequence_number"]


def test_no_random_module() -> None:
    """MockEngine must NOT use random module (hashlib determinism only)."""
    import inspect

    from coherence_bridge import mock_engine

    source = inspect.getsource(mock_engine)
    assert "import random" not in source, "MockEngine must use hashlib, not random"
    assert "random.gauss" not in source, "random.gauss found in MockEngine"
    assert "random.random" not in source, "random.random found in MockEngine"
