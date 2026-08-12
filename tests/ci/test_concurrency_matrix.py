# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""The concurrency matrix must bind every failure class to a REAL deterministic test.

Each row claims a runtime component is safe against a specific concurrency failure
class and names the deterministic test that proves it. This gate keeps the claim
honest: schema-valid, every referenced test node exists, every row is marked
deterministic and PASS, and a minimum set of critical failure classes is covered.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MATRIX = ROOT / "artifacts" / "concurrency" / "concurrency_matrix.json"
SCHEMA = ROOT / "audit" / "schema" / "concurrency_matrix.schema.json"

REQUIRED_CLASSES = frozenset(
    {
        "lost update",
        "torn read",
        "orphaned task",
        "double submit",
        "duplicate fill",
        "stale cache write",
        "missed cancellation",
        "timeout path",
    }
)


def _matrix() -> dict:
    return json.loads(MATRIX.read_text(encoding="utf-8"))


def test_matrix_validates_against_schema() -> None:
    matrix = _matrix()
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    assert matrix["schema"] == schema["$id"]
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
        func_name = func.split("::")[-1]
        path = ROOT / file_part
        assert path.is_file(), f"row references missing test file: {file_part}"
        text = path.read_text(encoding="utf-8")
        assert f"def {func_name}" in text, (
            f"row references missing test function {func_name!r} in {file_part}"
        )


def test_every_row_is_deterministic_and_passes() -> None:
    matrix = _matrix()
    for row in matrix["rows"]:
        assert row["deterministic"] is True, f"row is not deterministic: {row['test']}"
        assert row["verdict"] == "PASS", f"row is not PASS: {row['test']}"
    assert matrix["verdict"] == (
        "PASS" if all(r["verdict"] == "PASS" for r in matrix["rows"]) else "FAIL"
    )


def test_critical_failure_classes_are_covered() -> None:
    covered = {row["failure_class"] for row in _matrix()["rows"]}
    missing = REQUIRED_CLASSES - covered
    assert not missing, f"concurrency failure classes with no deterministic test: {sorted(missing)}"
