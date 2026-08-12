# mypy: disable-error-code="attr-defined,unused-ignore,no-untyped-call,call-overload,arg-type"
"""End-to-end integration test for CoherenceBridge pipeline.

Tests the complete signal path without Docker:
  MockEngine → _sanitize_signal → verify_signal → proto roundtrip
  → RegimeSignal dataclass → FeatureExporter → RiskGate → QuestDB mock

This is the smoke test that proves the entire stack is wired correctly.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from coherence_bridge.feature_exporter import RegimeFeatureExporter
from coherence_bridge.invariants import verify_signal
from coherence_bridge.mock_engine import MockEngine
from coherence_bridge.risk_gate import CoherenceRiskGate
from coherence_bridge.server import _sanitize_signal
from coherence_bridge.signal import Regime, RegimeSignal


def test_e2e_mock_to_feature_to_gate() -> None:
    """Full path: engine → sanitize → verify → signal → features → gate."""
    engine = MockEngine()
    exporter = RegimeFeatureExporter()
    gate = CoherenceRiskGate(engine, fail_closed=True)

    for _ in range(50):
        for inst in engine.instruments:
            # 1. Engine produces raw signal
            raw = engine.get_signal(inst)
            assert raw is not None

            # 2. Sanitize (fail-closed on NaN gamma)
            clean = _sanitize_signal(raw)

            # 3. Verify all 13 theorems
            results = verify_signal(clean, raise_on_failure=False)
            for r in results:
                assert r.passed, f"E2E {inst}: {r.theorem} failed: {r.message}"

            # 4. Construct typed signal
            sig = RegimeSignal.from_dict(clean)
            assert isinstance(sig.regime, Regime)
            assert sig.instrument == inst

            # 5. Export ML features
            features = exporter.to_ml_features(clean)
            assert len(features) == 7
            assert 0.0 <= features["r_coherence"] <= 1.0

            # 6. Risk gate decision
            decision = gate.apply(inst, 1.0)
            assert decision.adjusted_size <= 1.0
            assert decision.adjusted_size >= 0.0


def test_e2e_proto_roundtrip_preserves_typed_signal() -> None:
    """engine → dict → proto bytes → dict → RegimeSignal → verify."""
    from coherence_bridge.generated import coherence_bridge_pb2 as pb

    engine = MockEngine()
    regime_map = {
        "UNKNOWN": 0,
        "COHERENT": 1,
        "METASTABLE": 2,
        "DECOHERENT": 3,
        "CRITICAL": 4,
    }
    regime_rev = {v: k for k, v in regime_map.items()}

    for _ in range(20):
        raw = engine.get_signal("EURUSD")
        assert raw is not None
        clean = _sanitize_signal(raw)

        # Serialize
        proto = pb.RegimeSignal(
            timestamp_ns=int(clean["timestamp_ns"]),
            instrument=str(clean["instrument"]),
            gamma=float(clean["gamma"]),
            order_parameter_R=float(clean["order_parameter_R"]),
            ricci_curvature=float(clean["ricci_curvature"]),
            lyapunov_max=float(clean["lyapunov_max"]),
            regime=regime_map.get(str(clean["regime"]), 0),
            regime_confidence=float(clean.get("regime_confidence", 0)),
            regime_duration_s=float(clean.get("regime_duration_s", 0)),
            signal_strength=float(clean.get("signal_strength", 0)),
            risk_scalar=float(clean.get("risk_scalar", 0)),
            sequence_number=int(clean.get("sequence_number", 0)),
        )
        wire = proto.SerializeToString()

        # Deserialize
        restored_pb = pb.RegimeSignal()
        restored_pb.ParseFromString(wire)
        restored_dict = {
            "timestamp_ns": restored_pb.timestamp_ns,
            "instrument": restored_pb.instrument,
            "gamma": restored_pb.gamma,
            "order_parameter_R": restored_pb.order_parameter_R,
            "ricci_curvature": restored_pb.ricci_curvature,
            "lyapunov_max": restored_pb.lyapunov_max,
            "regime": regime_rev.get(restored_pb.regime, "UNKNOWN"),
            "regime_confidence": restored_pb.regime_confidence,
            "regime_duration_s": restored_pb.regime_duration_s,
            "signal_strength": restored_pb.signal_strength,
            "risk_scalar": restored_pb.risk_scalar,
            "sequence_number": restored_pb.sequence_number,
        }

        # Reconstruct typed signal
        sig = RegimeSignal.from_dict(restored_dict)
        assert sig.instrument == "EURUSD"
        assert isinstance(sig.regime, Regime)

        # Verify invariants survived the full trip
        for r in verify_signal(restored_dict, raise_on_failure=False):
            assert r.passed, f"E2E proto roundtrip: {r.theorem}: {r.message}"


def test_e2e_questdb_writer_called_with_valid_signal() -> None:
    """Verify QuestDB writer receives all 12 fields from sanitized signal."""
    writer = MagicMock()
    engine = MockEngine()

    for inst in engine.instruments:
        raw = engine.get_signal(inst)
        assert raw is not None
        clean = _sanitize_signal(raw)
        writer.write_signal(clean)

    assert writer.write_signal.call_count == len(engine.instruments)
    for call in writer.write_signal.call_args_list:
        sig = call[0][0]
        required = {
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
        assert required.issubset(set(sig.keys()))


def test_e2e_feature_exporter_dataframe() -> None:
    """Batch feature export → DataFrame with all columns."""
    engine = MockEngine()
    exporter = RegimeFeatureExporter()
    signals = []
    for _ in range(10):
        for inst in engine.instruments:
            raw = engine.get_signal(inst)
            if raw:
                signals.append(_sanitize_signal(raw))

    df = exporter.to_questdb_feature_table(signals)
    assert len(df) == 50
    assert "timestamp" in df.columns
    assert "gamma_distance" in df.columns
    assert "ricci_sign" in df.columns
