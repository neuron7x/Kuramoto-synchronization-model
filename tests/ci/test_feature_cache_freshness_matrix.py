# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""The feature-cache freshness matrix must bind every invariant to a real test.

Feature data served to live inference must never go backward in event time. This
gate keeps the freshness matrix honest: schema-valid, at least eight invariants,
each bound to an existing PASS test node, overall PASS only when every invariant
passes.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MATRIX = ROOT / "artifacts" / "cache" / "feature_cache_freshness_matrix.json"
SCHEMA = ROOT / "audit" / "schema" / "feature_cache_freshness_matrix.schema.json"


def _matrix() -> dict:
    return json.loads(MATRIX.read_text(encoding="utf-8"))


def test_matrix_validates_against_schema() -> None:
    matrix = _matrix()
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    assert matrix["schema"] == schema["$id"]
    assert len(matrix["invariants"]) >= 8
    try:
        import jsonschema
    except ImportError:
        return
    jsonschema.validate(matrix, schema)


def test_every_invariant_binds_an_existing_test() -> None:
    for inv in _matrix()["invariants"]:
        node = inv["test"]
        file_part, _, func = node.partition("::")
        path = ROOT / file_part
        assert path.is_file(), f"invariant {inv['id']} references missing file: {file_part}"
        text = path.read_text(encoding="utf-8")
        assert f"def {func}" in text, (
            f"invariant {inv['id']} references missing test {func!r} in {file_part}"
        )


def test_verdict_is_pass_iff_all_invariants_pass() -> None:
    matrix = _matrix()
    for inv in matrix["invariants"]:
        assert inv["verdict"] == "PASS", f"invariant not PASS: {inv['id']}"
    assert matrix["verdict"] == (
        "PASS" if all(i["verdict"] == "PASS" for i in matrix["invariants"]) else "FAIL"
    )
