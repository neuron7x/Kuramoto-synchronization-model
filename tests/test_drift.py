# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Unit tests for data drift detection utilities.

This module validates the drift detection mechanisms used to identify when
input data distributions change over time, which can degrade model performance.

Test Coverage:
- JS divergence: Jensen-Shannon divergence between distributions
- KS test: Kolmogorov-Smirnov test for distribution equality
- PSI: Population Stability Index for distribution shifts
- Parallel drift: Multi-column drift detection
- Drift detector: Comprehensive drift monitoring
- Edge cases: empty inputs, insufficient data, non-numeric columns
"""

import json

import numpy as np
import pandas as pd
import pytest

from geosync.utils.drift import (
    DriftDetector,
    DriftMetric,
    DriftTestResult,
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
    """Test Jensen-Shannon divergence computation for various distributions.

    JS divergence is a symmetric measure of difference between two probability
    distributions, ranging from 0 (identical) to 1 (completely different).

    Validates:
    - Identical distributions return divergence of 0
    - Different distributions return positive divergence values
    - Computed values match expected theoretical values
    """
    result = compute_js_divergence(np.asarray(data1), np.asarray(data2))
    assert (
        pytest.approx(result, rel=1e-3, abs=1e-6) == expected
    ), f"JS divergence mismatch: expected {expected}, got {result}"


def test_js_divergence_empty_inputs():
    """Test JS divergence returns NaN for empty input arrays.

    Empty inputs cannot form a valid probability distribution, so the
    function should return NaN rather than raising an exception.
    """
    result = compute_js_divergence([], [])
    assert np.isnan(result), f"Expected NaN for empty inputs, but got {result}"


def test_js_divergence_different_lengths_samples():
    """JS divergence should handle sample arrays with different lengths."""

    baseline = np.array([0.0, 0.0, 1.0, 1.0])
    current = np.array([0.0, 1.0, 1.0])

    result = compute_js_divergence(baseline, current)

    assert np.isfinite(result), "Expected finite JS divergence for sample arrays"
    assert result >= 0.0, "Divergence must be non-negative"
    assert pytest.approx(result, rel=1e-3, abs=1e-6) == 0.014362591564146746


@pytest.mark.parametrize(
    "data1,data2,drifted",
    [
        ([1, 2, 3, 4], [1, 2, 3, 4], False),
        ([1, 2, 3, 4, 5], [10, 11, 12, 13, 14], True),
    ],
)
def test_ks_test(data1, data2, drifted):
    """Test Kolmogorov-Smirnov test detects distribution drift.

    KS test should detect when two samples come from different distributions
    (p-value < 0.05) and accept when they come from the same distribution.

    Validates:
    - Test is valid for sufficient data
    - Identical distributions are not flagged as drifted
    - Significantly different distributions are detected
    """
    result = compute_ks_test(np.array(data1), np.array(data2))
    assert result.valid, f"KS test should be valid but got: {result.message}"
    assert (
        result.pvalue < 0.05
    ) == drifted, f"Expected drift={drifted} but p-value={result.pvalue:.4f} (threshold=0.05)"


def test_ks_test_insufficient_data():
    """Test KS test gracefully handles insufficient data.

    With only one sample per distribution, the KS test cannot produce
    reliable results, so it should return invalid status with NaN statistic.
    """
    result = compute_ks_test(np.array([1.0]), np.array([2.0]))
    assert not result.valid, "KS test should be invalid for single samples"
    assert np.isnan(
        result.statistic
    ), f"Expected NaN statistic for insufficient data, got {result.statistic}"


@pytest.mark.parametrize(
    "baseline,current,expected",
    [
        ([1, 2, 3, 4], [1, 2, 3, 4], 0.0),
        ([0, 0, 1, 1, 2, 2], [0, 1, 1, 2, 2, 2], pytest.approx(0.1831, rel=1e-3)),
    ],
)
def test_compute_psi(baseline, current, expected):
    """Test Population Stability Index (PSI) computation.

    PSI measures the shift in population distributions across bins:
    - PSI < 0.1: No significant change
    - 0.1 <= PSI < 0.2: Small change
    - PSI >= 0.2: Significant change requiring investigation

    Validates:
    - Identical distributions return PSI of 0
    - Shifted distributions return positive PSI values
    - Computed PSI matches expected values
    """
    result = compute_psi(np.array(baseline), np.array(current), bins=3)
    assert (
        pytest.approx(result, rel=1e-3, abs=1e-6) == expected
    ), f"PSI mismatch: expected {expected}, got {result}"


def test_compute_psi_ignores_nan_values():
    """PSI should drop NaN inputs instead of returning NaN for mixed payloads."""

    baseline = np.array([1.0, 1.0, np.nan, 1.0])
    current = np.array([1.0, 1.0, 1.0])

    result = compute_psi(baseline, current, bins=3)

    assert result == pytest.approx(0.0), "Identical distributions should yield zero PSI"


def test_parallel_drift():
    """Test parallel drift detection across multiple features.

    When generating synthetic data with drift_ratio=0.5, at least some
    features should show drift. The function should compute metrics for
    all features in parallel.

    Validates:
    - All features are analyzed
    - At least one feature shows drift
    - Results contain all expected columns
    """
    base, drift = generate_synthetic_data(200, 3, 0.5, seed=42)
    results = compute_parallel_drift(base, drift)
    assert set(results.keys()) == {
        "f0",
        "f1",
        "f2",
    }, f"Expected features f0, f1, f2 but got {set(results.keys())}"
    assert any(
        metric.drifted for metric in results.values()
    ), "Expected at least one feature to show drift with drift_ratio=0.5"


def test_parallel_drift_handles_non_numeric_columns():
    """Test drift detection gracefully handles categorical columns.

    Categorical columns cannot use numeric drift metrics (JS, KS, PSI),
    so the function should return NaN values and mark KS test as invalid.

    Validates:
    - Both numeric and categorical columns are processed
    - Categorical metrics return NaN
    - KS test is marked invalid with appropriate message
    - Numeric columns still get valid metrics
    """
    base = pd.DataFrame({"f0": [0.0, 1.0, 2.0], "category": ["A", "B", "A"]})
    drift = pd.DataFrame({"f0": [0.5, 1.5, 2.5], "category": ["B", "C", "B"]})
    results = compute_parallel_drift(base, drift)

    assert set(results.keys()) == {
        "f0",
        "category",
    }, f"Expected columns f0 and category, got {set(results.keys())}"
    cat_metric = results["category"]
    assert np.isnan(
        cat_metric.js_divergence
    ), f"Expected NaN JS divergence for categorical column, got {cat_metric.js_divergence}"
    assert not cat_metric.ks.valid, "KS test should be invalid for categorical data"
    assert (
        cat_metric.ks.message == "non-numeric column"
    ), f"Expected 'non-numeric column' message, got '{cat_metric.ks.message}'"
    assert np.isnan(
        cat_metric.psi
    ), f"Expected NaN PSI for categorical column, got {cat_metric.psi}"


def test_parallel_drift_coerces_numeric_strings():
    """Test drift detection coerces numeric strings to float.

    String columns that contain only numeric values should be automatically
    converted to numeric type for drift analysis.

    Validates:
    - String-encoded numbers are coerced to numeric
    - All drift metrics are computed successfully
    - Results are finite (not NaN or inf)
    """
    base = pd.DataFrame({"num": ["1", "2", "3", "4"]})
    drift = pd.DataFrame({"num": ["2", "3", "4", "5"]})
    results = compute_parallel_drift(base, drift)

    metric = results["num"]
    assert metric.ks.valid, "KS test should be valid after numeric coercion"
    assert np.isfinite(
        metric.js_divergence
    ), f"Expected finite JS divergence, got {metric.js_divergence}"
    assert np.isfinite(metric.psi), f"Expected finite PSI, got {metric.psi}"


def test_parallel_drift_filters_coerced_nans():
    """Test drift detection filters out values that can't be coerced to numeric.

    When coercing strings to numeric, invalid values should be filtered out
    rather than causing the entire analysis to fail.

    Validates:
    - Invalid numeric strings are filtered (e.g., "bad", None)
    - Valid numeric strings and whitespace-padded numbers are kept
    - Drift metrics are computed on remaining valid data
    - Drift is detected when distributions differ
    """
    base = pd.DataFrame({"num": ["1", "bad", None, "2", "\t3"]})
    drift = pd.DataFrame({"num": ["2", "bad", None, "3", "4"]})
    results = compute_parallel_drift(base, drift)

    metric = results["num"]
    assert metric.ks.valid, "KS test should be valid after filtering NaNs"
    assert np.isfinite(
        metric.js_divergence
    ), f"Expected finite JS divergence, got {metric.js_divergence}"
    assert np.isfinite(metric.psi), f"Expected finite PSI, got {metric.psi}"
    assert metric.js_divergence > 0, "Expected positive divergence for different distributions"


def test_drift_detector_summary():
    """Test DriftDetector generates comprehensive drift summary.

    The summary should include all features with their drift metrics
    (JS divergence, PSI, and KS test results).

    Validates:
    - Summary contains all expected features
    - Each feature has required metrics (jsd, psi)
    - Summary format is consistent and parseable
    """
    base, drift = generate_synthetic_data(200, 2, 0.0, seed=123)
    thresholds = DriftThresholds(default_jsd=0.05, default_ks=0.05)
    detector = DriftDetector(thresholds=thresholds)
    summary = detector.summary(detector.compare(base, drift))
    assert summary.keys() == {
        "f0",
        "f1",
    }, f"Expected features f0 and f1 in summary, got {summary.keys()}"
    assert all(
        "jsd" in value and "psi" in value for value in summary.values()
    ), "Each feature summary should contain 'jsd' and 'psi' metrics"


def test_compute_psi_accepts_unsorted_bins():
    """Explicit bin edges should be sanitised before histogramming."""

    baseline = [0.0, 0.5, 1.0, 1.5]
    current = [0.1, 0.4, 1.2, 1.4]

    unsorted_bins = [2.0, 0.0, 1.0]

    psi_value = compute_psi(baseline, current, bins=unsorted_bins)

    assert np.isfinite(psi_value)


def test_generate_synthetic_data_categorical():
    """Test synthetic data generation includes categorical features.

    When include_categorical=True, the generated data should contain
    both numeric and categorical columns.

    Validates:
    - Categorical column is present in baseline data
    - Baseline and drift datasets have same shape
    - Categorical column exists in both datasets
    """
    base, drift = generate_synthetic_data(100, 2, 0.3, seed=7, include_categorical=True)
    assert (
        "category" in base.columns
    ), f"Expected 'category' column in baseline, got columns: {list(base.columns)}"
    assert (
        base.shape == drift.shape
    ), f"Shape mismatch: baseline {base.shape} vs drift {drift.shape}"


def test_load_thresholds_empty_yaml(tmp_path):
    """Test loading thresholds from empty YAML uses defaults.

    When the threshold configuration file is empty, the function should
    return default threshold values rather than raising an error.

    Validates:
    - Empty YAML files are handled gracefully
    - Default JS divergence threshold is 0.1
    - Default KS test threshold is 0.05
    """
    cfg_path = tmp_path / "thresholds.yaml"
    cfg_path.write_text("")
    thresholds = load_thresholds(cfg_path)
    assert (
        thresholds.default_jsd == 0.1
    ), f"Expected default JSD threshold of 0.1, got {thresholds.default_jsd}"
    assert (
        thresholds.default_ks == 0.05
    ), f"Expected default KS threshold of 0.05, got {thresholds.default_ks}"


def test_load_thresholds_requires_mapping(tmp_path):
    """Test loading thresholds fails gracefully for invalid YAML structure.

    The threshold configuration should be a mapping (dict), not a list.
    Invalid structure should raise TypeError with informative message.

    Validates:
    - List-structured YAML is rejected
    - TypeError is raised for invalid structure
    - Function validates input format
    """
    cfg_path = tmp_path / "thresholds.yaml"
    cfg_path.write_text("- 0.1\n- 0.2\n")
    with pytest.raises(TypeError, match=".+"):
        load_thresholds(cfg_path)


def test_drift_metric_respects_thresholds_overrides():
    metric = DriftMetric(
        feature="f0",
        js_divergence=0.05,
        ks=DriftTestResult(statistic=0.1, pvalue=0.02, valid=True, message="ok"),
        psi=0.05,
    )
    thresholds = DriftThresholds(default_jsd=0.1, default_ks=0.05, default_psi=0.1)

    assert metric.drifted, "Legacy drift flag should remain permissive"
    assert metric.drifted_with_thresholds(thresholds=thresholds, feature="f0") is True
    assert (
        metric.drifted_with_thresholds(thresholds=thresholds, feature="f0", alpha=0.01) is False
    ), "Alpha override should tighten KS detection"


def test_load_thresholds_supports_psi_thresholds(tmp_path):
    cfg_path = tmp_path / "thresholds.json"
    cfg_path.write_text(
        json.dumps(
            {
                "jsd_threshold": 0.2,
                "ks_pvalue_threshold": 0.01,
                "psi_threshold": 0.25,
                "thresholds": {"custom": {"psi": 0.5}},
            }
        )
    )

    thresholds = load_thresholds(cfg_path)

    assert thresholds.default_psi == 0.25
    assert thresholds.threshold_for("custom", "psi") == 0.5
