# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""The causal prefix-invariance matrix must bind every surface to a real test.

Future input must not change past output. This gate keeps the matrix honest:
schema-valid, >= 6 time-indexed surfaces, each bound to an existing PASS
prefix-invariance test node.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MATRIX = ROOT / "artifacts" / "time" / "causal_prefix_matrix.json"
SCHEMA = ROOT / "audit" / "schema" / "causal_prefix_matrix.schema.json"


def _matrix() -> dict:
    return json.loads(MATRIX.read_text(encoding="utf-8"))


def test_matrix_validates_against_schema() -> None:
    matrix = _matrix()
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    assert matrix["schema"] == schema["$id"]
    assert len(matrix["surfaces"]) >= 6
    try:
        import jsonschema
    except ImportError:
        return
    jsonschema.validate(matrix, schema)


def test_every_surface_binds_an_existing_test() -> None:
    for row in _matrix()["surfaces"]:
        node = row["test"]
        file_part, _, func = node.partition("::")
        path = ROOT / file_part
        assert path.is_file(), f"surface {row['surface']} references missing file: {file_part}"
        text = path.read_text(encoding="utf-8")
        assert f"def {func}" in text, (
            f"surface {row['surface']} references missing test {func!r} in {file_part}"
        )


def test_verdict_is_pass_iff_all_surfaces_pass() -> None:
    matrix = _matrix()
    for row in matrix["surfaces"]:
        assert row["verdict"] == "PASS", f"surface not PASS: {row['surface']}"
    assert matrix["verdict"] == (
        "PASS" if all(r["verdict"] == "PASS" for r in matrix["surfaces"]) else "FAIL"
    )
