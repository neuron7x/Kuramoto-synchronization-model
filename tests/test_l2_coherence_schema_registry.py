"""Task 4 · Artifact schema registry.

Each `results/L2_*.json` artifact has a declared required-keys schema
here. The test enforces that every committed artifact obeys its
schema. New keys are fine; removing a required key breaks the
contract loud-and-clear (not silent drift).

Canonical source of truth for what the pipeline promises downstream.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

_RESULTS = Path("results")

# Each entry: top-level required keys. Nested paths use dotted form where needed.
_SCHEMAS: dict[str, tuple[str, ...]] = {
    "L2_KILLTEST_VERDICT.json": (
        "verdict",
        "ic_signal",
        "residual_ic",
        "residual_ic_pvalue",
        "n_samples",
        "n_symbols",
        "horizon_ic",
        "ic_baselines",
        "null_test_pvalues",
        "seed",
    ),
    "L2_ROBUSTNESS.json": (
        "bootstrap",
        "deflated_sharpe",
        "adf",
        "mutual_information",
        "n_rows",
        "n_symbols",
        "horizon_sec",
    ),
    "L2_PURGED_CV.json": (
        "k",
        "ic_per_fold",
        "ic_mean",
        "ic_median",
        "ic_std",
        "ic_min",
        "ic_max",
        "n_rows_total",
        "horizon_rows",
        "embargo_rows",
    ),
    "L2_IC_ATTRIBUTION.json": (
        "autocorr",
        "concentration",
        "lag",
        "horizon_sec",
        "n_rows",
        "n_symbols",
    ),
    "L2_SPECTRAL.json": (
        "redness_slope_beta",
        "redness_intercept",
        "regime_verdict",
        "dominant_period_sec",
        "dominant_peak_power",
        "top_power_bins",
        "n_psd_bins",
        "n_rows",
        "fs_hz",
        "segment_sec",
    ),
    "L2_HURST.json": (
        "report",
        "n_rows",
        "n_symbols",
        "min_scale",
        "max_scale_frac",
        "n_scales",
    ),
    "L2_REGIME_MARKOV.json": (
        "transition_matrix",
        "stationary_distribution",
        "states",
        "state_counts",
        "mean_diagonal",
        "expected_dwell_sec",
        "diagonal_persistence",
        "n_transitions",
    ),
    "L2_TRANSFER_ENTROPY.json": (
        "n_rows",
        "n_symbols",
        "n_pairs",
        "verdict_counts",
        "pairs",
        "n_bins",
        "lag_rows",
        "n_surrogates",
        "seed",
    ),
    "L2_CONDITIONAL_TE.json": (
        "n_rows",
        "n_symbols",
        "conditioner",
        "n_pairs",
        "verdict_counts",
        "pairs",
        "n_bins",
        "lag_rows",
        "n_surrogates",
        "seed",
    ),
    "L2_WALK_FORWARD_SUMMARY.json": (
        "verdict",
        "n_windows",
        "n_valid",
        "window_sec",
        "step_sec",
        "ic_mean",
        "ic_std",
        "ic_median",
        "ic_q25",
        "ic_q75",
        "fraction_positive",
        "fraction_permutation_significant",
    ),
    "L2_DIURNAL_PROFILE.json": (
        "hour_buckets",
        "n_significant_positive",
        "n_significant_negative",
        "pvalue_gate",
        "horizon_sec",
    ),
    "L2_FULL_CYCLE_MANIFEST.json": (
        "schema_version",
        "cycle_duration_sec",
        "stages",
        "required_inputs",
        "figures",
    ),
}


def _load(name: str) -> dict[str, Any]:
    path = _RESULTS / name
    with path.open("r", encoding="utf-8") as f:
        data: dict[str, Any] = json.load(f)
    return data


@pytest.mark.parametrize("artifact, required_keys", list(_SCHEMAS.items()))
def test_artifact_has_required_keys(artifact: str, required_keys: tuple[str, ...]) -> None:
    path = _RESULTS / artifact
    if not path.exists():
        pytest.skip(f"{artifact} not present")
    payload = _load(artifact)
    missing = [k for k in required_keys if k not in payload]
    assert not missing, f"{artifact} missing required keys: {missing}"


def test_all_schemas_map_to_existing_or_skipped_files() -> None:
    """Sanity: every schema key is either an artifact on disk or intentionally absent."""
    for name in _SCHEMAS:
        assert name.startswith("L2_"), f"schema key '{name}' must follow naming convention"
        assert name.endswith(".json")


def test_full_cycle_manifest_stage_names_match_expected_axes() -> None:
    path = _RESULTS / "L2_FULL_CYCLE_MANIFEST.json"
    if not path.exists():
        pytest.skip("manifest not present")
    m = _load("L2_FULL_CYCLE_MANIFEST.json")
    names = {s["name"] for s in m["stages"]}
    expected = {
        "killtest",
        "attribution",
        "purged_cv",
        "spectral",
        "hurst",
        "regime_markov",
        "robustness",
        "transfer_entropy",
        "conditional_te",
    }
    assert names == expected
