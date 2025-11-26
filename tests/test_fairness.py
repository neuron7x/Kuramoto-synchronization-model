from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from src.risk import evaluate_fairness, write_fairness_report


@pytest.mark.parametrize(
    "y_true,y_pred,groups,expected",
    [
        (
            [1, 0, 1, 0],
            [1, 0, 1, 0],
            ["A", "A", "B", "B"],
            {"demographic_parity": 0.0, "equal_opportunity": 0.0},
        ),
        (
            [1, 1, 1, 1],
            [1, 1, 0, 0],
            ["A", "A", "B", "B"],
            {"demographic_parity": 1.0, "equal_opportunity": 1.0},
        ),
    ],
)
def test_evaluate_fairness_outputs_expected_metrics(
    y_true, y_pred, groups, expected
) -> None:
    evaluation = evaluate_fairness(y_true, y_pred, groups)

    assert evaluation.demographic_parity == pytest.approx(
        expected["demographic_parity"]
    )
    assert evaluation.equal_opportunity == pytest.approx(expected["equal_opportunity"])


def test_write_fairness_report(tmp_path: Path) -> None:
    y_true = np.array([1, 1, 0, 0])
    y_pred = np.array([1, 1, 0, 0])
    groups = np.array(["A", "A", "B", "B"])

    evaluation = evaluate_fairness(y_true, y_pred, groups)

    output = tmp_path / "reports" / "fairness_report.json"
    write_fairness_report(evaluation, output_path=output)

    assert output.exists()

    content = json.loads(output.read_text(encoding="utf-8"))
    assert "demographic_parity" in content
    assert "equal_opportunity" in content
    assert "thresholds" in content

    npz_path = output.with_suffix(".npz")
    assert npz_path.exists()
    with np.load(npz_path) as npz:
        assert "demographic_parity" in npz.files
        assert "equal_opportunity" in npz.files
