# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for `scripts/analysis_null_convergence.py` (Task 3)."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from research.robustness.protocols.kuramoto_contract import (
    KuramotoRobustnessContract,
)
from research.robustness.protocols.kuramoto_null_suite import (
    run_kuramoto_null_suite,
)


@pytest.fixture(scope="module")
def contract() -> KuramotoRobustnessContract:
    return KuramotoRobustnessContract.from_frozen_artifacts()


class TestNullConvergenceDeterminism:
    def test_same_seed_same_p_values(self, contract: KuramotoRobustnessContract) -> None:
        """Same seed + same n_trials must produce bit-identical p-values."""
        a = run_kuramoto_null_suite(contract, n_bootstrap=500, seed=42)
        b = run_kuramoto_null_suite(contract, n_bootstrap=500, seed=42)
        for fa, fb in zip(a.families, b.families, strict=True):
            assert fa.p_value == fb.p_value
            assert fa.null_sharpes == fb.null_sharpes

    def test_same_seed_different_n_gives_different_p(
        self, contract: KuramotoRobustnessContract
    ) -> None:
        """Changing n_trials while holding seed constant must produce
        distinct p-values (sanity check that n_trials is actually
        wired through)."""
        a = run_kuramoto_null_suite(contract, n_bootstrap=500, seed=42)
        b = run_kuramoto_null_suite(contract, n_bootstrap=1000, seed=42)
        # At least one family must differ in at least the 4th decimal.
        diffs = [
            abs(fa.p_value - fb.p_value) for fa, fb in zip(a.families, b.families, strict=True)
        ]
        assert any(d > 1e-5 for d in diffs)


class TestNullConvergenceCSVSchema:
    def test_csv_has_required_columns(self) -> None:
        """Regression test on the on-disk `null_convergence.csv` emitted
        by `scripts/analysis_null_convergence.py`. Columns are required
        by the ROBUSTNESS_RESULTS.md reader in
        `scripts/run_kuramoto_robustness_v1.py::_read_convergence`."""
        csv_path = (
            Path(__file__).resolve().parents[3]
            / "results"
            / "cross_asset_kuramoto"
            / "robustness_v1"
            / "null_convergence.csv"
        )
        if not csv_path.is_file():
            pytest.skip("null_convergence.csv absent — run scripts/analysis_null_convergence.py")
        with csv_path.open(encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            assert reader.fieldnames is not None
            required = {
                "n_trials",
                "family_id",
                "observed_sharpe",
                "p_value",
                "p_value_pass",
            }
            assert required <= set(reader.fieldnames)
            rows = list(reader)
        # Four trial counts × two families = 8 rows.
        assert len(rows) == 8
        trial_values = {int(r["n_trials"]) for r in rows}
        assert trial_values == {500, 1000, 2000, 5000}
        families = {r["family_id"] for r in rows}
        assert families == {"iid_bootstrap", "stationary_bootstrap"}
