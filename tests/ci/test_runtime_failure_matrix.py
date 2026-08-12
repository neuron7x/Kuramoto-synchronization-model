# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""The runtime failure matrix must be schema-valid and every row must bind a
REAL, existing fail-closed test.

The matrix is an evidence artifact: it claims that for a given component and a
plausible runtime failure class, a specific test proves the component fails
closed (typed failure / explicit degraded verdict / exception) rather than
returning a fake success. This gate keeps that claim honest — the referenced
test node must exist, every row must assert fail_closed→fail_closed→PASS, and a
minimum set of critical failure classes must be covered.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MATRIX = ROOT / "artifacts" / "runtime_failure_matrix" / "runtime_failure_matrix.json"
SCHEMA = ROOT / "audit" / "schema" / "runtime_failure_matrix.schema.json"

# Failure classes that MUST be represented by at least one real test.
REQUIRED_CLASSES = frozenset(
    {
        "secret leakage",
        "future leakage",
        "NaN/Infinity",
        "empty input",
        "wrong hash",
        "unknown enum/status",
        "threshold boundary",
        "non-atomic commit",
    }
)


def _matrix() -> dict:
    return json.loads(MATRIX.read_text(encoding="utf-8"))


def test_matrix_validates_against_schema() -> None:
    matrix = _matrix()
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    assert matrix["schema"] == schema["$id"]
    # Structural floor (always) + full jsonschema when available.
    assert isinstance(matrix["rows"], list) and matrix["rows"]
    assert matrix["verdict"] in ("PASS", "FAIL")
    try:
        import jsonschema
    except ImportError:
        return
    jsonschema.validate(matrix, schema)


def test_every_referenced_test_node_exists() -> None:
    for row in _matrix()["rows"]:
        node = row["test"]
        file_part, _, func = node.partition("::")
        func_name = func.split("::")[-1]  # Class::method -> method
        path = ROOT / file_part
        assert path.is_file(), f"row references missing test file: {file_part}"
        text = path.read_text(encoding="utf-8")
        assert f"def {func_name}" in text, (
            f"row references missing test function {func_name!r} in {file_part}"
        )


def test_every_row_asserts_fail_closed_and_passes() -> None:
    matrix = _matrix()
    for row in matrix["rows"]:
        assert row["expected_behavior"] == "fail_closed"
        assert row["observed_behavior"] == "fail_closed"
        assert row["verdict"] == "PASS", f"row is not PASS: {row['component']}/{row['failure_class']}"
    # Overall verdict is PASS iff every row passes.
    assert matrix["verdict"] == ("PASS" if all(r["verdict"] == "PASS" for r in matrix["rows"]) else "FAIL")


def test_critical_failure_classes_are_covered() -> None:
    covered = {row["failure_class"] for row in _matrix()["rows"]}
    missing = REQUIRED_CLASSES - covered
    assert not missing, f"critical runtime failure classes have no fail-closed test: {sorted(missing)}"
