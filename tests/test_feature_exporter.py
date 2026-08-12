"""Tests for RF meta-labeling feature export."""

from __future__ import annotations

import time

from coherence_bridge.feature_exporter import RegimeFeatureExporter

EXPECTED_KEYS = {
    "gamma_distance",
    "r_coherence",
    "ricci_sign",
    "lyapunov_sign",
    "regime_encoded",
    "regime_confidence",
    "risk_scalar",
}


def _signal(**overrides) -> dict:
    base = {
        "timestamp_ns": time.time_ns(),
        "instrument": "EURUSD",
        "gamma": 0.8,
        "order_parameter_R": 0.6,
        "ricci_curvature": -0.3,
        "lyapunov_max": 0.02,
        "regime": "METASTABLE",
        "regime_confidence": 0.85,
        "risk_scalar": 0.8,
    }
    base.update(overrides)
    return base


def test_to_ml_features_has_7_keys() -> None:
    features = RegimeFeatureExporter.to_ml_features(_signal())
    assert set(features.keys()) == EXPECTED_KEYS


def test_gamma_distance_is_abs_from_metastable() -> None:
    f = RegimeFeatureExporter.to_ml_features(_signal(gamma=1.3))
    assert abs(f["gamma_distance"] - 0.3) < 1e-10


def test_ricci_sign_negative() -> None:
    f = RegimeFeatureExporter.to_ml_features(_signal(ricci_curvature=-0.5))
    assert f["ricci_sign"] == -1.0


def test_ricci_sign_positive() -> None:
    f = RegimeFeatureExporter.to_ml_features(_signal(ricci_curvature=0.3))
    assert f["ricci_sign"] == 1.0


def test_lyapunov_sign_chaotic() -> None:
    f = RegimeFeatureExporter.to_ml_features(_signal(lyapunov_max=0.05))
    assert f["lyapunov_sign"] == 1.0


def test_lyapunov_sign_stable() -> None:
    f = RegimeFeatureExporter.to_ml_features(_signal(lyapunov_max=-0.02))
    assert f["lyapunov_sign"] == -1.0


def test_regime_encoding() -> None:
    for regime, code in [
        ("COHERENT", 0),
        ("METASTABLE", 1),
        ("DECOHERENT", 2),
        ("CRITICAL", 3),
    ]:
        f = RegimeFeatureExporter.to_ml_features(_signal(regime=regime))
        assert f["regime_encoded"] == float(code)


def test_to_questdb_feature_table() -> None:
    signals = [_signal(instrument=f"PAIR{i}") for i in range(5)]
    df = RegimeFeatureExporter.to_questdb_feature_table(signals)
    assert len(df) == 5
    assert "timestamp" in df.columns
    assert "instrument" in df.columns
    assert "gamma_distance" in df.columns
