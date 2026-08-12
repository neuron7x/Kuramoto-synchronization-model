"""Tests for the consolidated headline metrics JSON."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from research.microstructure.headline_metrics import build_headline_metrics
from tests.l2_artifacts import load_results_artifact


@pytest.fixture(scope="module")
def metrics() -> dict[str, Any]:
    return load_results_artifact("L2_HEADLINE_METRICS.json")


# Flat-schema contract keys — downstream promises
_REQUIRED_KEYS: frozenset[str] = frozenset(
    {
        "kill_test_verdict",
        "ic_pooled",
        "ic_residual",
        "residual_p_value",
        "n_rows",
        "n_symbols",
        "bootstrap_ci_lo_95",
        "bootstrap_ci_hi_95",
        "bootstrap_significant_at_95",
        "deflated_sharpe",
        "probability_sharpe_is_real",
        "purged_cv_mean_ic",
        "purged_cv_median_ic",
        "purged_cv_n_folds",
        "mutual_information_nats",
        "mutual_information_bits",
        "spectral_beta",
        "spectral_regime_verdict",
        "spectral_dominant_period_sec",
        "hurst_exponent",
        "hurst_r_squared",
        "hurst_verdict",
        "te_bidirectional_count",
        "te_n_pairs",
        "cte_private_flow_count",
        "cte_n_pairs",
        "cte_conditioner",
        "walk_forward_verdict",
        "walk_forward_fraction_positive",
        "walk_forward_ic_median",
        "walk_forward_ic_std",
        "regime_conditional_verdict",
        "regime_conditional_ratio_high_over_low",
        "ic_high_vol",
        "ic_low_vol",
        "ablation_hyperparam_verdict",
        "ablation_hyperparam_max_rel_drift",
        "ablation_symbol_verdict",
        "ablation_symbol_min_ic",
        "ablation_hold_verdict",
        "ablation_slippage_verdict",
        "ablation_slippage_max_viable_bp",
        "ablation_fee_verdict",
        "ablation_fee_max_viable_bp",
    }
)


def test_every_required_key_is_present(metrics: dict[str, Any]) -> None:
    missing = _REQUIRED_KEYS - metrics.keys()
    assert not missing, f"required keys absent: {sorted(missing)}"


def test_schema_values_are_primitive(metrics: dict[str, Any]) -> None:
    """Downstream contract: every value must be primitive or None, never nested."""
    for k, v in metrics.items():
        assert v is None or isinstance(
            v, (int, float, str, bool)
        ), f"key '{k}' has non-primitive type {type(v).__name__}: {v!r}"


def test_headline_ic_matches_killtest(metrics: dict[str, Any]) -> None:
    killtest = load_results_artifact("L2_KILLTEST_VERDICT.json")
    assert abs(float(metrics["ic_pooled"]) - float(killtest["ic_signal"])) < 1e-12


def test_headline_beta_matches_spectral(metrics: dict[str, Any]) -> None:
    spectral = load_results_artifact("L2_SPECTRAL.json")
    assert abs(float(metrics["spectral_beta"]) - float(spectral["redness_slope_beta"])) < 1e-12


def test_builder_degrades_gracefully_on_missing_inputs(tmp_path: Path) -> None:
    """On an empty results dir, builder returns dict with all keys set to None."""
    out = build_headline_metrics(tmp_path)
    missing_keys = _REQUIRED_KEYS - out.keys()
    assert not missing_keys, f"schema incomplete: {sorted(missing_keys)}"
    # Every value should be None (degraded gracefully, not raised)
    for k, v in out.items():
        assert v is None, f"expected {k} to be None on missing input; got {v!r}"
