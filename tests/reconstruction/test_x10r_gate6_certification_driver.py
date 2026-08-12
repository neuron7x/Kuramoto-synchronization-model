# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""D-002B — tests for the certification-sweep driver helpers.

Pure unit tests on the aggregation and verdict-classification logic
in `scripts/run_x10r_gate6_certification_sweep.py`. The driver is
imported by module path so these tests stay fast and never run a
Kuramoto sim — they validate ONLY the pipeline plumbing.

Strict scope: synthetic / unit only. NO real-data path. NO INV lift.

Bibliographic anchors justify model class and reviewer traceability;
operational validity is determined only by gates, positive/negative
controls, null distributions, capsules, and power/FPR/MDE evidence.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from research.reconstruction.sensitivity_surface import (
    SensitivityCell,
    SensitivitySurface,
)

_DRIVER_PATH = (
    Path(__file__).resolve().parents[2] / "scripts" / "run_x10r_gate6_certification_sweep.py"
)


def _load_driver() -> ModuleType:
    spec = importlib.util.spec_from_file_location("d002b_driver", _DRIVER_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def driver() -> ModuleType:
    return _load_driver()


def _result_row(
    *,
    n: int = 50,
    lam: float = 1.0,
    seed_idx: int = 0,
    passed: bool = True,
    direction: str = "SYNCHRONIZATION_FACILITATED",
    delta_r_median: float = 0.10,
    ci_width: float = 0.05,
) -> dict[str, Any]:
    return {
        "n": n,
        "lam": lam,
        "seed_idx": seed_idx,
        "passed": passed,
        "direction": direction,
        "delta_r_median": delta_r_median,
        "ci_width": ci_width,
    }


def test_aggregate_counts_pass_and_directions(driver: ModuleType) -> None:
    rows = [
        _result_row(seed_idx=i, passed=(i < 4), direction="SYNCHRONIZATION_FACILITATED")
        for i in range(5)
    ]
    surface = driver._aggregate_to_surface(rows, n_grid=(50,), lambda_grid=(1.0,), n_seeds=5)
    cell = surface.cell(n=50, lambda_mix=1.0)
    assert cell is not None
    assert cell.n_pass == 4
    assert cell.n_facilitated == 5
    assert cell.n_hindered == 0
    assert cell.n_no_signal == 0
    assert cell.power == pytest.approx(0.8)


def test_aggregate_handles_no_signal_direction(driver: ModuleType) -> None:
    rows = [_result_row(passed=False, direction="NO_SIGNAL", seed_idx=i) for i in range(3)]
    surface = driver._aggregate_to_surface(rows, n_grid=(50,), lambda_grid=(1.0,), n_seeds=3)
    cell = surface.cell(n=50, lambda_mix=1.0)
    assert cell is not None
    assert cell.n_no_signal == 3
    assert cell.power == 0.0


def test_aggregate_separates_distinct_cells(driver: ModuleType) -> None:
    rows = [_result_row(n=50, lam=0.0, seed_idx=i, passed=False) for i in range(2)]
    rows += [_result_row(n=50, lam=1.0, seed_idx=i, passed=True) for i in range(2)]
    surface = driver._aggregate_to_surface(rows, n_grid=(50,), lambda_grid=(0.0, 1.0), n_seeds=2)
    c0 = surface.cell(n=50, lambda_mix=0.0)
    c1 = surface.cell(n=50, lambda_mix=1.0)
    assert c0 is not None and c0.n_pass == 0
    assert c1 is not None and c1.n_pass == 2
    assert surface.fpr_estimate == 0.0


def test_aggregate_mde_per_n_unreached_is_inf(driver: ModuleType) -> None:
    rows = [_result_row(n=50, lam=1.0, seed_idx=i, passed=False) for i in range(5)]
    surface = driver._aggregate_to_surface(rows, n_grid=(50,), lambda_grid=(1.0,), n_seeds=5)
    assert surface.mde_lambda_per_n[50] == float("inf")


def test_aggregate_mde_per_n_reached_at_first_passing_lambda(
    driver: ModuleType,
) -> None:
    rows = [_result_row(n=50, lam=0.10, seed_idx=i, passed=False) for i in range(5)]
    rows += [_result_row(n=50, lam=0.40, seed_idx=i, passed=True) for i in range(5)]
    surface = driver._aggregate_to_surface(rows, n_grid=(50,), lambda_grid=(0.10, 0.40), n_seeds=5)
    assert surface.mde_lambda_per_n[50] == 0.40


def test_classify_certifies_when_all_three_rules_pass(driver: ModuleType) -> None:
    cells = [
        SensitivityCell(
            n_nodes=50,
            lambda_mix=0.0,
            n_seeds=20,
            n_pass=0,
            n_facilitated=0,
            n_hindered=0,
            n_no_signal=20,
            median_delta_r=0.0,
            median_ci_width=0.05,
            median_abs_delta_r=0.005,
        ),
        SensitivityCell(
            n_nodes=50,
            lambda_mix=0.40,
            n_seeds=20,
            n_pass=18,
            n_facilitated=18,
            n_hindered=0,
            n_no_signal=2,
            median_delta_r=0.10,
            median_ci_width=0.04,
            median_abs_delta_r=0.10,
        ),
        SensitivityCell(
            n_nodes=50,
            lambda_mix=1.0,
            n_seeds=20,
            n_pass=20,
            n_facilitated=20,
            n_hindered=0,
            n_no_signal=0,
            median_delta_r=0.20,
            median_ci_width=0.05,
            median_abs_delta_r=0.20,
        ),
    ]
    surface = SensitivitySurface(
        n_grid=(50,),
        lambda_grid=(0.0, 0.40, 1.0),
        n_seeds=20,
        cells=tuple(cells),
        fpr_estimate=0.0,
        mde_lambda_per_n={50: 0.40},
    )
    verdict, metrics = driver._classify(surface)
    assert verdict == "SYNTHETIC_GATE6_CERTIFIED"
    assert metrics["fpr_rule_pass"] is True
    assert metrics["power_rule_pass"] is True
    assert metrics["ci_vs_dr_pass"] is True


def test_classify_rejects_when_fpr_too_high(driver: ModuleType) -> None:
    cells = [
        SensitivityCell(
            n_nodes=50,
            lambda_mix=0.0,
            n_seeds=20,
            n_pass=5,  # 25 % FPR > 5 %
            n_facilitated=5,
            n_hindered=0,
            n_no_signal=15,
            median_delta_r=0.02,
            median_ci_width=0.05,
            median_abs_delta_r=0.02,
        ),
        SensitivityCell(
            n_nodes=50,
            lambda_mix=1.0,
            n_seeds=20,
            n_pass=20,
            n_facilitated=20,
            n_hindered=0,
            n_no_signal=0,
            median_delta_r=0.20,
            median_ci_width=0.05,
            median_abs_delta_r=0.20,
        ),
    ]
    surface = SensitivitySurface(
        n_grid=(50,),
        lambda_grid=(0.0, 1.0),
        n_seeds=20,
        cells=tuple(cells),
        fpr_estimate=0.25,
        mde_lambda_per_n={50: 1.0},
    )
    verdict, metrics = driver._classify(surface)
    assert verdict == "GATE6_NOT_CERTIFIED_AT_TESTED_BUDGET"
    assert metrics["fpr_rule_pass"] is False


def test_classify_rejects_when_power_below_threshold(driver: ModuleType) -> None:
    cells = [
        SensitivityCell(
            n_nodes=50,
            lambda_mix=0.0,
            n_seeds=20,
            n_pass=0,
            n_facilitated=0,
            n_hindered=0,
            n_no_signal=20,
            median_delta_r=0.0,
            median_ci_width=0.05,
            median_abs_delta_r=0.005,
        ),
        SensitivityCell(
            n_nodes=50,
            lambda_mix=0.40,
            n_seeds=20,
            n_pass=10,  # 50 % power < 80 %
            n_facilitated=10,
            n_hindered=0,
            n_no_signal=10,
            median_delta_r=0.05,
            median_ci_width=0.05,
            median_abs_delta_r=0.05,
        ),
    ]
    surface = SensitivitySurface(
        n_grid=(50,),
        lambda_grid=(0.0, 0.40),
        n_seeds=20,
        cells=tuple(cells),
        fpr_estimate=0.0,
        mde_lambda_per_n={50: float("inf")},
    )
    verdict, metrics = driver._classify(surface)
    assert verdict == "GATE6_NOT_CERTIFIED_AT_TESTED_BUDGET"
    assert metrics["power_rule_pass"] is False


def test_classify_rejects_when_ci_width_dominates_at_lambda_one(
    driver: ModuleType,
) -> None:
    cells = [
        SensitivityCell(
            n_nodes=50,
            lambda_mix=0.0,
            n_seeds=20,
            n_pass=0,
            n_facilitated=0,
            n_hindered=0,
            n_no_signal=20,
            median_delta_r=0.0,
            median_ci_width=0.02,
            median_abs_delta_r=0.005,
        ),
        SensitivityCell(
            n_nodes=50,
            lambda_mix=0.40,
            n_seeds=20,
            n_pass=18,
            n_facilitated=18,
            n_hindered=0,
            n_no_signal=2,
            median_delta_r=0.10,
            median_ci_width=0.05,
            median_abs_delta_r=0.10,
        ),
        SensitivityCell(
            n_nodes=50,
            lambda_mix=1.0,
            n_seeds=20,
            n_pass=20,
            n_facilitated=20,
            n_hindered=0,
            n_no_signal=0,
            median_delta_r=0.05,
            median_ci_width=0.30,  # CI > |ΔR|
            median_abs_delta_r=0.05,
        ),
    ]
    surface = SensitivitySurface(
        n_grid=(50,),
        lambda_grid=(0.0, 0.40, 1.0),
        n_seeds=20,
        cells=tuple(cells),
        fpr_estimate=0.0,
        mde_lambda_per_n={50: 0.40},
    )
    verdict, metrics = driver._classify(surface)
    assert verdict == "GATE6_NOT_CERTIFIED_AT_TESTED_BUDGET"
    assert metrics["ci_vs_dr_pass"] is False
