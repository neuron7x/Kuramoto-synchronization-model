# mypy: disable-error-code="attr-defined,unused-ignore,no-untyped-call,arg-type,type-arg"
"""Tests for MetaCognitionLayer — система бачить себе."""

from __future__ import annotations

from unittest.mock import MagicMock

from geosync.neuroeconomics.metacognition import (
    ModelRegime,
    CalibrationSnapshot,
    _classify,
    CalibrationDriftDetector,
    IndependentWitness,
    MetaCognitionLayer,
    ModelGamma,
    ModelGammaEstimator,
    PredictionErrorMonitor,
)


def _sig(regime: str = "METASTABLE", gamma: float = 1.0, confidence: float = 0.8) -> dict:
    return {
        "instrument": "EURUSD",
        "regime": regime,
        "gamma": gamma,
        "regime_confidence": confidence,
        "risk_scalar": 0.75,
        "order_parameter_R": 0.6,
        "ricci_curvature": 0.1,
        "lyapunov_max": -0.05,
        "signal_strength": 0.3,
    }


def _dec(d: str = "TRADE") -> MagicMock:
    m = MagicMock()
    m.decision.value = d
    return m


def _rm(expected: str = "METASTABLE") -> MagicMock:
    m = MagicMock()
    m.get_expected_next.return_value = expected
    return m


# === PredictionErrorMonitor ===


def test_correct_prediction_zero_error() -> None:
    mon = PredictionErrorMonitor()
    mon.record_prediction("EURUSD", "METASTABLE", 0.9)
    err = mon.observe_outcome("EURUSD", "METASTABLE")
    assert err is not None
    assert err.error_magnitude == 0.0
    assert not err.is_overconfident


def test_wrong_high_confidence_overconfident() -> None:
    mon = PredictionErrorMonitor()
    mon.record_prediction("EURUSD", "COHERENT", 0.95)
    err = mon.observe_outcome("EURUSD", "CRITICAL")
    assert err is not None
    assert err.is_overconfident
    assert err.error_magnitude > 0.9


def test_no_prediction_returns_none() -> None:
    assert PredictionErrorMonitor().observe_outcome("X", "Y") is None


# === CalibrationDriftDetector ===


def test_paralysis_detected() -> None:
    det = CalibrationDriftDetector(window=50)
    for _ in range(50):
        det.record("OBSERVE")
    assert det.snapshot().is_paralyzed


def test_reckless_detected() -> None:
    det = CalibrationDriftDetector(window=50)
    for _ in range(50):
        det.record("TRADE")
    assert det.snapshot().is_reckless


def test_healthy_low_drift() -> None:
    det = CalibrationDriftDetector(window=100)
    for _ in range(47):
        det.record("TRADE")
    for _ in range(37):
        det.record("OBSERVE")
    for _ in range(16):
        det.record("ABORT")
    snap = det.snapshot()
    assert snap.drift_score < 0.10
    assert not snap.is_paralyzed and not snap.is_reckless


# === ModelGammaEstimator ===


def test_gamma_model_bounded() -> None:
    est = ModelGammaEstimator(window=50)
    for _ in range(50):
        est.record_decision("ABORT")
    mg = est.estimate(1.5)
    assert 0.1 <= mg.gamma_model <= 3.0


def test_resonance_computable() -> None:
    est = ModelGammaEstimator(window=50)
    for i in range(50):
        est.record_decision(["TRADE", "OBSERVE", "ABORT"][i % 3])
    mg = est.estimate(1.0)
    assert 0.0 <= mg.resonance <= 1.0


# === IndependentWitness ===


def test_witness_ok_on_healthy() -> None:
    w = IndependentWitness()
    cal = CalibrationDriftDetector(window=100)
    for _ in range(47):
        cal.record("TRADE")
    for _ in range(37):
        cal.record("OBSERVE")
    for _ in range(16):
        cal.record("ABORT")
    mg = ModelGamma(gamma_model=1.0, gamma_market=1.0, resonance=0.95, is_resonant=True)
    alert, reason = w.assess(cal.snapshot(), mg, 0.05, 0.1)
    assert not alert
    assert reason == "OK"


def test_witness_fires_on_resonance_break() -> None:
    w = IndependentWitness()
    cal = CalibrationDriftDetector(window=100)
    for _ in range(47):
        cal.record("TRADE")
    for _ in range(37):
        cal.record("OBSERVE")
    for _ in range(16):
        cal.record("ABORT")
    mg = ModelGamma(gamma_model=2.5, gamma_market=0.8, resonance=0.1, is_resonant=False)
    alert, reason = w.assess(cal.snapshot(), mg, 0.05, 0.1)
    assert alert
    assert "RESONANCE" in reason


def test_blind_spot_detection() -> None:
    w = IndependentWitness()
    for _ in range(10):
        w.record_error("CRITICAL", 0.9)
    assert w.detect_blind_spot() == "CRITICAL"


# === MetaCognitionLayer integration ===


def test_kelly_meta_bounded() -> None:
    meta = MetaCognitionLayer()
    for i in range(30):
        state = meta.observe(
            _sig(regime=["METASTABLE", "COHERENT", "DECOHERENT"][i % 3]),
            _dec(["TRADE", "OBSERVE", "ABORT"][i % 3]),
            _rm(),
        )
        assert 0.1 <= state.kelly_meta_multiplier <= 1.0


def test_meta_features_keys() -> None:
    meta = MetaCognitionLayer()
    state = meta.observe(_sig(), _dec(), _rm())
    features = meta.get_meta_features(state)
    assert set(features.keys()) == {
        "gamma_model",
        "gamma_resonance",
        "calibration_drift",
        "cumulative_pred_error",
        "meta_confidence",
        "witness_alert",
    }


def test_witness_fires_on_all_observe() -> None:
    meta = MetaCognitionLayer()
    for _ in range(250):
        state = meta.observe(_sig(regime="DECOHERENT"), _dec("OBSERVE"), _rm("DECOHERENT"))
    assert state.calibration.is_paralyzed or state.witness_alert


def test_should_recalibrate_on_all_trade() -> None:
    meta = MetaCognitionLayer()
    for _ in range(250):
        state = meta.observe(_sig(), _dec("TRADE"), _rm())
    assert state.should_recalibrate


def test_gamma_estimator_needs_twenty_decisions_before_estimating() -> None:
    """`if len(decision_vals) < 20` -- below the window it returns the neutral
    default, above it computes from variance.

    Under Lt->GtE the guard inverts: <20 decisions would compute on thin data and
    >=20 would freeze at the default.
    """
    thin = ModelGammaEstimator()
    for _ in range(10):
        thin.record_decision("OBSERVE")
    assert thin.estimate(0.1).gamma_model == 1.0  # neutral default

    full = ModelGammaEstimator()
    for _ in range(25):
        full.record_decision("OBSERVE")  # zero variance -> gamma_model clips to 0.1
    assert full.estimate(0.1).gamma_model == 0.1  # computed, not default


def test_gamma_resonance_flag_tracks_market_distance() -> None:
    """`is_resonant = resonance > RESONANCE_THRESHOLD` -- close markets resonate.

    Under Gt->LtE a near-matching market reads non-resonant and a distant one
    resonant.
    """
    est = ModelGammaEstimator()
    for _ in range(25):
        est.record_decision("OBSERVE")  # gamma_model -> 0.1
    assert est.estimate(0.1).is_resonant is True  # distance 0 -> resonance 1.0
    assert est.estimate(2.0).is_resonant is False  # distance 1.9 -> resonance 0.05


def test_witness_error_buffer_capped_above_fifty() -> None:
    """`if len(errs) > 50` caps the per-regime error buffer.

    Under Gt->LtE the cap never fires (unbounded growth) and a sub-50 buffer
    would instead be truncated.
    """
    witness = IndependentWitness()
    for i in range(51):
        witness.record_error("CRITICAL", float(i))
    assert len(witness._regime_errors["CRITICAL"]) == 50


def test_classify_flags_drifting_above_alert_threshold() -> None:
    """`if cal.drift_score > DRIFT_ALERT_THRESHOLD` -> DRIFTING regime.

    Under Gt->LtE a genuinely drifting calibration (0.30 > 0.25) is no longer
    classified as DRIFTING.
    """
    resonant = ModelGamma(gamma_model=1.0, gamma_market=1.0, resonance=1.0, is_resonant=True)
    drifting_cal = CalibrationSnapshot(0.47, 0.37, 0.16, drift_score=0.30, is_paralyzed=False, is_reckless=False)
    assert _classify(resonant, drifting_cal, False) is ModelRegime.DRIFTING
