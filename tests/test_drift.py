import numpy as np
import pandas as pd
import pytest

from tradepulse.utils.drift import (
    DriftDetector,
    DriftThresholds,
    compute_js_divergence,
    compute_ks_test,
    compute_parallel_drift,
    compute_psi,
    generate_synthetic_data,
    load_thresholds,
)


@pytest.mark.parametrize(
    "data1,data2,expected",
    [
        ([0.2, 0.8], [0.2, 0.8], 0.0),
        ([0.5, 0.5], [0.9, 0.1], pytest.approx(0.1017, rel=1e-3)),
    ],
)
def test_js_divergence(data1, data2, expected):
    result = compute_js_divergence(np.asarray(data1), np.asarray(data2))
    assert pytest.approx(result, rel=1e-3, abs=1e-6) == expected


def test_js_divergence_empty_inputs():
    assert np.isnan(compute_js_divergence([], []))


@pytest.mark.parametrize(
    "data1,data2,drifted",
    [
        ([1, 2, 3, 4], [1, 2, 3, 4], False),
        ([1, 2, 3, 4, 5], [10, 11, 12, 13, 14], True),
    ],
)
def test_ks_test(data1, data2, drifted):
    result = compute_ks_test(np.array(data1), np.array(data2))
    assert result.valid
    assert (result.pvalue < 0.05) == drifted


def test_ks_test_insufficient_data():
    result = compute_ks_test(np.array([1.0]), np.array([2.0]))
    assert not result.valid
    assert np.isnan(result.statistic)


@pytest.mark.parametrize(
    "baseline,current,expected",
    [
        ([1, 2, 3, 4], [1, 2, 3, 4], 0.0),
        ([0, 0, 1, 1, 2, 2], [0, 1, 1, 2, 2, 2], pytest.approx(0.1831, rel=1e-3)),
    ],
)
def test_compute_psi(baseline, current, expected):
    result = compute_psi(np.array(baseline), np.array(current), bins=3)
    assert pytest.approx(result, rel=1e-3, abs=1e-6) == expected


def test_parallel_drift():
    base, drift = generate_synthetic_data(200, 3, 0.5, seed=42)
    results = compute_parallel_drift(base, drift)
    assert set(results.keys()) == {"f0", "f1", "f2"}
    assert any(metric.drifted for metric in results.values())


def test_drift_detector_summary():
    base, drift = generate_synthetic_data(200, 2, 0.0, seed=123)
    thresholds = DriftThresholds(default_jsd=0.05, default_ks=0.05)
    detector = DriftDetector(thresholds=thresholds)
    summary = detector.summary(detector.compare(base, drift))
    assert summary.keys() == {"f0", "f1"}
    assert all("jsd" in value and "psi" in value for value in summary.values())


def test_generate_synthetic_data_categorical():
    base, drift = generate_synthetic_data(100, 2, 0.3, seed=7, include_categorical=True)
    assert "category" in base.columns
    assert base.shape == drift.shape


def test_load_thresholds_empty_yaml(tmp_path):
    cfg_path = tmp_path / "thresholds.yaml"
    cfg_path.write_text("")
    thresholds = load_thresholds(cfg_path)
    assert thresholds.default_jsd == 0.1
    assert thresholds.default_ks == 0.05


def test_load_thresholds_requires_mapping(tmp_path):
    cfg_path = tmp_path / "thresholds.yaml"
    cfg_path.write_text("- 0.1\n- 0.2\n")
    with pytest.raises(TypeError):
        load_thresholds(cfg_path)
