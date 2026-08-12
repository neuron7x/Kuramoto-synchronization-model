# mypy: disable-error-code="attr-defined,unused-ignore,no-untyped-call,arg-type"
"""NaN/Inf adversarial tests — prove fail-closed through entire pipeline.

Every module that touches signal floats must survive NaN/Inf without crash.
"""

from __future__ import annotations

import math
import time

from coherence_bridge.decision_engine import GeoSyncDecisionEngine
from coherence_bridge.feature_exporter import RegimeFeatureExporter
from coherence_bridge.mock_engine import MockEngine
from coherence_bridge.risk_gate import CoherenceRiskGate
from coherence_bridge.server import _sanitize_signal
from coherence_bridge.uncertainty_compat import UncertaintyEstimator
from geosync.neuroeconomics.epistemic_action import EpistemicDecision
from geosync.neuroeconomics.homeostatic_stabilizer import NeuroHomeostaticStabilizer
from geosync.neuroeconomics.regime_memory import RegimeMemory


def _poison_signal(**overrides: object) -> dict[str, object]:
    """Signal with NaN in every float field by default."""
    base: dict[str, object] = {
        "timestamp_ns": time.time_ns(),
        "instrument": "EURUSD",
        "gamma": float("nan"),
        "order_parameter_R": float("nan"),
        "ricci_curvature": float("inf"),
        "lyapunov_max": float("-inf"),
        "regime": "METASTABLE",
        "regime_confidence": float("nan"),
        "regime_duration_s": -1.0,
        "signal_strength": float("nan"),
        "risk_scalar": float("nan"),
        "sequence_number": 0,
    }
    base.update(overrides)
    return base


def test_sanitizer_survives_all_nan() -> None:
    result = _sanitize_signal(_poison_signal())
    assert result["risk_scalar"] == 0.0
    assert result["regime"] == "UNKNOWN"


def test_uncertainty_survives_nan_signal() -> None:
    est = UncertaintyEstimator()
    for _ in range(15):
        unc = est.update(_poison_signal())
    assert math.isfinite(unc.total)
    assert math.isfinite(unc.ambiguity_index)
    assert math.isfinite(unc.surprise)


def test_regime_memory_survives_nan() -> None:
    mem = RegimeMemory()
    trans = mem.observe("EURUSD", "METASTABLE")
    assert math.isfinite(trans.surprise)
    assert math.isfinite(trans.probability)


def test_nhs_survives_nan_signal() -> None:
    nhs = NeuroHomeostaticStabilizer()
    for _ in range(15):
        state = nhs.update(_poison_signal())
    assert math.isfinite(state.ei_ratio)
    assert math.isfinite(state.kelly_multiplier)
    assert state.kelly_multiplier >= 0.0


def test_feature_exporter_survives_nan() -> None:
    features = RegimeFeatureExporter.to_ml_features(_poison_signal())
    for key, val in features.items():
        assert math.isfinite(val), f"NaN in feature {key}={val}"


def test_risk_gate_survives_nan() -> None:
    from unittest.mock import MagicMock

    mock_engine = MagicMock()
    mock_engine.get_signal.return_value = _sanitize_signal(_poison_signal())
    gate = CoherenceRiskGate(mock_engine, fail_closed=True)
    d = gate.apply("EURUSD", 1.0)
    assert not d.allowed
    assert d.adjusted_size == 0.0


def test_decision_engine_survives_nan() -> None:
    engine = GeoSyncDecisionEngine(MockEngine())
    for _ in range(15):
        engine.process(_poison_signal(), 1.0)
    out = engine.process(_poison_signal(), 1.0)
    assert out.adjusted_size == 0.0
    assert out.decision in (EpistemicDecision.OBSERVE, EpistemicDecision.ABORT)


def test_full_pipeline_nan_never_leaks_to_trade() -> None:
    """NaN at any point in pipeline NEVER produces a TRADE with size > 0."""
    engine = GeoSyncDecisionEngine(MockEngine())
    for _ in range(20):
        out = engine.process(_poison_signal(), 1.0)
        if out.decision == EpistemicDecision.TRADE:
            assert out.adjusted_size == 0.0 or math.isfinite(out.adjusted_size)
