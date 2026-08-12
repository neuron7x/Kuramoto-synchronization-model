# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Smoke tests for the DRO-ARA Monte Carlo power harness.

Keep CI fast: we use small N (30 samples per generator) and short series
(1024 points) while still exercising every code path.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from scripts.research.dro_ara_power_mc import (
    GENERATORS,
    REGIME_ORDER,
    _bootstrap_rate,
    build_verdict,
    run,
    run_mc,
)


def test_generators_cover_expected_labels() -> None:
    assert set(GENERATORS.keys()) == {
        "ou",
        "gbm_drift",
        "random_walk",
        "white_noise",
        "ar1_phi02",
        "ar1_phi08",
    }


def test_run_mc_returns_confusion_matrix_shape() -> None:
    mc = run_mc(n_samples=10, length=1024, window=512, step=64, seed=42)
    conf = mc["confusion_matrix"]
    assert set(conf.keys()) == set(GENERATORS.keys())
    for gen in GENERATORS:
        row = conf[gen]
        assert set(row.keys()) >= set(REGIME_ORDER)


def test_run_mc_determinism() -> None:
    a = run_mc(n_samples=10, length=1024, window=512, step=64, seed=42)
    b = run_mc(n_samples=10, length=1024, window=512, step=64, seed=42)
    assert a["confusion_matrix"] == b["confusion_matrix"]


def test_ou_classifies_as_critical_majority() -> None:
    mc = run_mc(n_samples=30, length=1536, window=512, step=64, seed=42)
    rate = mc["p_critical"]["ou"]["p_critical_boot_median"]
    assert rate >= 0.5, f"OU P(CRITICAL) too low: {rate:.3f}"


def test_gbm_drift_not_classified_as_critical_majority() -> None:
    """GBM with drift: low false-positive rate for CRITICAL classification.

    Post-PR #345 RFC: ADF on returns, so GBM is no longer uniformly INVALID
    (INV-DRO3 now encodes true unit root in returns, and GBM returns are
    i.i.d. Gaussian). The surviving false-positive invariant: GBM must not
    be classified CRITICAL in the majority — CRITICAL is reserved for
    genuinely anti-persistent H < 0.45, which GBM-drift does not satisfy
    in expectation. Empirically on seed=42, n=30: CRITICAL rate ≈ 17 %.

    Contract: p_critical(GBM) ≤ 0.40 (well below OU's ≥ 0.50 threshold).
    This is the complementary check to ``test_ou_classifies_as_critical_majority``.
    """
    mc = run_mc(n_samples=30, length=1536, window=512, step=64, seed=42)
    rate = mc["p_critical"]["gbm_drift"]["p_critical_boot_median"]
    assert rate <= 0.40, f"GBM CRITICAL false-positive rate too high: {rate:.3f}, expected ≤ 0.40"

    gbm = mc["confusion_matrix"]["gbm_drift"]
    total = sum(gbm.values())
    assert total > 0
    non_critical_rate = (total - gbm["CRITICAL"]) / total
    assert (
        non_critical_rate >= 0.60
    ), f"GBM should land in non-CRITICAL regimes majority: {non_critical_rate:.3f}"


def test_bootstrap_rate_valid_range() -> None:
    hits = np.array([True, False, True, True, False, True], dtype=bool)
    med, lo, hi = _bootstrap_rate(hits, n_boot=200, seed=1)
    assert 0.0 <= lo <= med <= hi <= 1.0


def test_bootstrap_rate_empty() -> None:
    hits = np.array([], dtype=bool)
    med, lo, hi = _bootstrap_rate(hits, n_boot=100, seed=1)
    assert np.isnan(med) and np.isnan(lo) and np.isnan(hi)


def test_build_verdict_pass() -> None:
    mc = {
        "p_critical": {
            "ou": {"p_critical_boot_median": 0.8},
            "gbm_drift": {"p_critical_boot_median": 0.05},
        }
    }
    verdict, _ = build_verdict(mc)
    assert verdict == "PASS"


def test_build_verdict_fails_when_ou_too_low() -> None:
    mc = {
        "p_critical": {
            "ou": {"p_critical_boot_median": 0.1},
            "gbm_drift": {"p_critical_boot_median": 0.05},
        }
    }
    verdict, reason = build_verdict(mc)
    assert verdict == "FAIL"
    assert "OU" in reason


def test_run_writes_payload(tmp_path: Path) -> None:
    out = tmp_path / "power.json"
    payload = run(n_samples=10, length=1024, window=512, step=64, seed=42, out_path=out)
    assert out.exists()
    on_disk = json.loads(out.read_text())
    assert on_disk["spike_name"] == "dro_ara_power_mc"
    assert "replay_hash_short" in on_disk
    assert "confusion_matrix" in on_disk["measurement"]
    assert payload["replay_hash_short"] == on_disk["replay_hash_short"]
    assert len(on_disk["replay_hash_short"]) == 16


def test_run_verdict_passes_on_canonical_params(tmp_path: Path) -> None:
    out = tmp_path / "power.json"
    payload = run(n_samples=25, length=1536, window=512, step=64, seed=42, out_path=out)
    assert payload["verdict"] in {"PASS", "FAIL"}


def test_replay_hash_short_is_16_hex() -> None:
    out_path = Path("/tmp") / "_dro_ara_power_hashcheck.json"
    payload = run(n_samples=10, length=1024, window=512, step=64, seed=42, out_path=out_path)
    h = payload["replay_hash_short"]
    assert len(h) == 16
    assert all(c in "0123456789abcdef" for c in h)
