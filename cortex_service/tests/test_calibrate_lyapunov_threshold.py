# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import csv
import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from cortex_service.scripts.calibrate_lyapunov_threshold import (
    Point,
    build_candidate_grid,
    calibrate_threshold,
    evaluate_threshold,
    load_points,
    result_to_dict,
    split_points,
    transition_steps,
    validate_candidates,
)


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["step", "lyapunov", "regime_label"]
        )
        writer.writeheader()
        writer.writerows(rows)


def load_points_from_rows(rows: list[dict[str, object]]) -> list[Point]:
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", delete=False, encoding="utf-8"
    ) as handle:
        tmp = Path(handle.name)
    _write_csv(tmp, rows)
    return load_points(tmp)


def _contract_rows() -> list[dict[str, object]]:
    return [
        {"step": 1, "lyapunov": 0.05, "regime_label": "steady"},
        {"step": 2, "lyapunov": 0.60, "regime_label": "steady"},
        {"step": 3, "lyapunov": 0.10, "regime_label": "shifted"},
        {"step": 4, "lyapunov": 0.05, "regime_label": "shifted"},
        {"step": 5, "lyapunov": 0.90, "regime_label": "shifted"},
        {"step": 6, "lyapunov": 0.10, "regime_label": "shifted"},
        {"step": 7, "lyapunov": 0.10, "regime_label": "steady"},
        {"step": 8, "lyapunov": 0.10, "regime_label": "steady"},
    ]


def _contract_points() -> list[Point]:
    return load_points_from_rows(_contract_rows())


def _forbidden_claim_terms() -> list[str]:
    term_parts = [
        ("b", "uy"),
        ("s", "ell"),
        ("l", "ong"),
        ("s", "hort"),
        ("en", "try"),
        ("ex", "it"),
        ("al", "pha"),
        ("ed", "ge"),
        ("pro", "fit"),
        ("trading", " signal"),
        ("pred", "ictor"),
        ("guaran", "teed"),
        ("market", " call"),
        ("price", " direction"),
    ]
    return ["".join(parts) for parts in term_parts]


def test_load_points_valid_csv(tmp_path: Path) -> None:
    path = tmp_path / "data.csv"
    _write_csv(
        path,
        [
            {"step": 1, "lyapunov": 0.4, "regime_label": "neutral"},
            {"step": 2, "lyapunov": 0.8, "regime_label": "shifted"},
        ],
    )
    points = load_points(path)
    assert len(points) == 2
    assert points[1].label == "shifted"


def test_load_points_missing_columns_raises(tmp_path: Path) -> None:
    path = tmp_path / "broken.csv"
    path.write_text("step,lyapunov\n1,0.5\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Missing columns"):
        load_points(path)


def test_load_points_rejects_nan(tmp_path: Path) -> None:
    path = tmp_path / "nan.csv"
    _write_csv(path, [{"step": 1, "lyapunov": math.nan, "regime_label": "neutral"}])
    with pytest.raises(ValueError, match="finite"):
        load_points(path)


def test_transition_steps_empty_single_multiple() -> None:
    assert transition_steps([]) == []
    single = load_points_from_rows(
        [{"step": 1, "lyapunov": 0.1, "regime_label": "neutral"}]
    )
    assert transition_steps(single) == []
    pts = load_points_from_rows(
        [
            {"step": 1, "lyapunov": 0.1, "regime_label": "neutral"},
            {"step": 2, "lyapunov": 0.2, "regime_label": "neutral"},
            {"step": 3, "lyapunov": 0.3, "regime_label": "shifted"},
            {"step": 4, "lyapunov": 0.4, "regime_label": "shifted"},
            {"step": 5, "lyapunov": 0.5, "regime_label": "neutral"},
        ]
    )
    assert transition_steps(pts) == [3, 5]


def test_evaluate_threshold_no_transitions() -> None:
    pts = load_points_from_rows(
        [
            {"step": 1, "lyapunov": 0.2, "regime_label": "neutral"},
            {"step": 2, "lyapunov": 0.3, "regime_label": "neutral"},
        ]
    )
    mean_lead, covered = evaluate_threshold(pts, 0.4)
    assert mean_lead == 0.0
    assert covered == 0


def test_evaluate_threshold_known_leadtime() -> None:
    pts = load_points_from_rows(
        [
            {"step": 1, "lyapunov": 0.1, "regime_label": "neutral"},
            {"step": 2, "lyapunov": 0.8, "regime_label": "neutral"},
            {"step": 3, "lyapunov": 0.2, "regime_label": "shifted"},
        ]
    )
    mean_lead, covered = evaluate_threshold(pts, 0.7)
    assert mean_lead == 1.0
    assert covered == 1


def test_build_candidate_grid_and_allowed_range() -> None:
    assert build_candidate_grid(0.2, 0.4, 0.1) == (0.2, 0.3, 0.4)
    assert validate_candidates([0.4, 0.2, 0.2], (0.2, 0.4)) == (0.2, 0.4)
    with pytest.raises(ValueError, match="outside allowed range"):
        validate_candidates([0.1], (0.2, 0.4))
    with pytest.raises(ValueError, match="finite"):
        validate_candidates([math.inf], (0.2, 0.4))
    with pytest.raises(ValueError, match="positive"):
        build_candidate_grid(0.2, 0.4, 0.0)


def test_split_points_separates_calibration_from_validation() -> None:
    calibration, validation, calibration_id, validation_id = split_points(
        _contract_points(), calibration_fraction=0.5
    )
    assert calibration[-1].step < validation[0].step
    assert calibration_id == "steps:1-4"
    assert validation_id == "steps:5-8"
    with pytest.raises(ValueError, match="between 0 and 1"):
        split_points(_contract_points(), calibration_fraction=1.0)
    with pytest.raises(ValueError, match="at least four points"):
        split_points(_contract_points()[:3], calibration_fraction=0.5)


def test_calibration_result_is_deterministic_and_order_independent() -> None:
    points = _contract_points()
    first = calibrate_threshold(
        points,
        candidates=[0.8, 0.2, 0.6],
        allowed_range=(0.2, 0.8),
        calibration_fraction=0.5,
        seed=7,
    )
    second = calibrate_threshold(
        points,
        candidates=[0.6, 0.8, 0.2],
        allowed_range=(0.2, 0.8),
        calibration_fraction=0.5,
        seed=7,
    )
    assert first == second
    assert first.selected_value == 0.2


def test_tie_policy_selects_lowest_threshold() -> None:
    result = calibrate_threshold(
        _contract_points(),
        candidates=[0.2, 0.6],
        allowed_range=(0.2, 0.6),
        calibration_fraction=0.5,
    )
    assert result.tie_policy == "lowest_threshold_on_equal_calibration_score"
    assert result.selected_value == 0.2


def test_validation_split_does_not_select_candidate() -> None:
    result = calibrate_threshold(
        _contract_points(),
        candidates=[0.2, 0.8],
        allowed_range=(0.2, 0.8),
        calibration_fraction=0.5,
    )
    sweep = {row.candidate: row for row in result.sensitivity_sweep}
    assert sweep[0.8].validation_metric > 0.0
    assert sweep[0.8].calibration_metric == 0.0
    assert result.selected_value == 0.2


def test_degenerate_inputs_fail_closed() -> None:
    with pytest.raises(ValueError, match="candidate grid"):
        calibrate_threshold(
            _contract_points(),
            candidates=[],
            allowed_range=(0.2, 0.8),
            calibration_fraction=0.5,
        )
    with pytest.raises(ValueError, match="no threshold coverage"):
        calibrate_threshold(
            _contract_points(),
            candidates=[0.95],
            allowed_range=(0.9, 1.0),
            calibration_fraction=0.5,
        )


def test_metadata_and_sensitivity_sweep_are_complete() -> None:
    result = calibrate_threshold(
        _contract_points(),
        candidates=[0.2, 0.6, 0.8],
        allowed_range=(0.2, 0.8),
        calibration_fraction=0.5,
        seed=11,
    )
    data = result_to_dict(result)

    required = {
        "method",
        "parameter_name",
        "candidate_values",
        "selected_value",
        "metric_name",
        "metric_values",
        "calibration_count",
        "validation_count",
        "invalid_count",
        "seed",
        "tie_policy",
        "sensitivity_band",
        "failure_policy",
        "not_financial_advice",
        "not_predictive_claim",
        "calibration_dataset",
        "validation_dataset",
        "objective",
        "allowed_range",
        "selection_rule",
        "sensitivity_sweep",
    }
    assert required <= set(data)
    assert result.calibration_count == 4
    assert result.validation_count == 4
    assert len(result.sensitivity_sweep) == 3
    assert {row.candidate for row in result.sensitivity_sweep} == {0.2, 0.6, 0.8}


def test_no_forbidden_claim_language_in_metadata() -> None:
    result = calibrate_threshold(
        _contract_points(),
        candidates=[0.2, 0.6],
        allowed_range=(0.2, 0.6),
        calibration_fraction=0.5,
    )
    encoded = json.dumps(result_to_dict(result), sort_keys=True).lower()
    assert not any(term in encoded for term in _forbidden_claim_terms())


def test_main_e2e_json_metadata(tmp_path: Path) -> None:
    path = tmp_path / "data.csv"
    _write_csv(path, _contract_rows())
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "cortex_service.scripts.calibrate_lyapunov_threshold",
            "--csv",
            str(path),
            "--min",
            "0.2",
            "--max",
            "0.8",
            "--step",
            "0.2",
            "--calibration-fraction",
            "0.5",
            "--json",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    assert payload["selected_value"] == 0.2
    assert payload["calibration_dataset"] == "steps:1-4"
    assert payload["validation_dataset"] == "steps:5-8"


def test_main_e2e_text_keeps_threshold_summary(tmp_path: Path) -> None:
    path = tmp_path / "data.csv"
    _write_csv(path, _contract_rows())
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "cortex_service.scripts.calibrate_lyapunov_threshold",
            "--csv",
            str(path),
            "--min",
            "0.2",
            "--max",
            "0.8",
            "--step",
            "0.2",
            "--calibration-fraction",
            "0.5",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "best_threshold=0.200" in result.stdout
