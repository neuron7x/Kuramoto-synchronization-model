import numpy as np
import pandas as pd
import pytest

from src.data.etl.monitoring import DriftDetector


def _baseline_frame(seed: int = 1234) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    return pd.DataFrame(
        {
            "price": rng.normal(0.0, 1.5, size=1024),
            "volume": rng.lognormal(0.1, 0.4, size=1024),
        }
    )


def test_drift_detector_calibration_updates_threshold_and_details() -> None:
    baseline = _baseline_frame()
    detector = DriftDetector(threshold=0.05, bins=20)

    result = detector.calibrate(
        baseline,
        quantile=0.9,
        iterations=12,
        sample_size=128,
        random_state=7,
    )

    assert detector.threshold == pytest.approx(result.threshold)
    assert result.quantile == pytest.approx(0.9)
    assert result.iterations == 12
    assert result.sample_size == 128
    assert set(result.divergences) == {"price", "volume"}
    assert all(len(scores) == 12 for scores in result.divergences.values())

    combined = [score for scores in result.divergences.values() for score in scores]
    expected = np.quantile(np.asarray(combined), 0.9)
    assert result.threshold == pytest.approx(float(expected))


def test_drift_detector_calibration_respects_apply_flag() -> None:
    baseline = pd.DataFrame(
        {"constant": np.ones(32), "category": ["a", "b", "c", "d"] * 8}
    )
    detector = DriftDetector(threshold=0.2, bins=8)

    result = detector.calibrate(
        baseline,
        quantile=0.8,
        iterations=4,
        random_state=11,
        apply=False,
    )

    assert detector.threshold == pytest.approx(0.2)
    assert result.divergences["constant"] == (0.0, 0.0, 0.0, 0.0)
    assert result.threshold == pytest.approx(0.0)


def test_drift_detector_calibration_handles_non_numeric_frames() -> None:
    baseline = pd.DataFrame({"state": ["ok", "ok", "bad", "ok"]})
    detector = DriftDetector(threshold=0.3)

    result = detector.calibrate(baseline, iterations=5, random_state=5)

    assert detector.threshold == pytest.approx(0.3)
    assert result.divergences == {}
    assert result.threshold == pytest.approx(0.3)


def test_drift_detector_calibration_validates_arguments() -> None:
    baseline = _baseline_frame()
    detector = DriftDetector()

    with pytest.raises(ValueError):
        detector.calibrate(baseline, quantile=1.0)

    with pytest.raises(ValueError):
        detector.calibrate(baseline, iterations=0)

    with pytest.raises(ValueError):
        detector.calibrate(baseline, sample_size=1)
