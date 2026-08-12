# mypy: disable-error-code="attr-defined,operator,index,arg-type,call-overload,assignment"
"""Proto compilation and serialization roundtrip tests."""

from coherence_bridge.generated import coherence_bridge_pb2 as pb


def test_regime_enum_values() -> None:
    assert pb.REGIME_UNKNOWN == 0
    assert pb.REGIME_COHERENT == 1
    assert pb.REGIME_METASTABLE == 2
    assert pb.REGIME_DECOHERENT == 3
    assert pb.REGIME_CRITICAL == 4


def test_regime_signal_roundtrip() -> None:
    sig = pb.RegimeSignal(
        timestamp_ns=1_700_000_000_000_000_000,
        instrument="EURUSD",
        gamma=1.05,
        order_parameter_R=0.73,
        ricci_curvature=-0.12,
        lyapunov_max=0.003,
        regime=pb.REGIME_METASTABLE,
        regime_confidence=0.85,
        regime_duration_s=42.5,
        signal_strength=0.15,
        risk_scalar=0.95,
        sequence_number=42,
    )
    data = sig.SerializeToString()
    restored = pb.RegimeSignal()
    restored.ParseFromString(data)

    assert restored.instrument == "EURUSD"
    assert restored.regime == pb.REGIME_METASTABLE
    assert abs(restored.gamma - 1.05) < 1e-10
    assert abs(restored.order_parameter_R - 0.73) < 1e-10
    assert abs(restored.risk_scalar - 0.95) < 1e-10
    assert restored.sequence_number == 42


def test_signal_request() -> None:
    req = pb.SignalRequest(instruments=["EURUSD", "GBPUSD"], min_interval_ms=500)
    assert len(req.instruments) == 2
    assert req.min_interval_ms == 500


def test_health_response_map() -> None:
    resp = pb.HealthResponse(
        healthy=True,
        uptime_s=120,
        signals_emitted=1000,
        last_signal_ts={"EURUSD": 123456789, "GBPUSD": 987654321},
    )
    assert resp.last_signal_ts["EURUSD"] == 123456789
    assert resp.signals_emitted == 1000


def test_empty_signal_defaults() -> None:
    sig = pb.RegimeSignal()
    assert sig.timestamp_ns == 0
    assert sig.instrument == ""
    assert sig.gamma == 0.0
    assert sig.regime == pb.REGIME_UNKNOWN
    assert sig.sequence_number == 0
