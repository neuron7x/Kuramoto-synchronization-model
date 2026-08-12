# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""The apex adversarial-soundness report must bind every attack to a real test.

Lightweight (json + pathlib only, no heavy neuro import) so it collects in the
minimal repo-integrity env. It keeps the adversarial taxonomy honest: schema-valid,
>=5 attacks, each marked defeated and bound to an existing test node.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "artifacts" / "inference" / "apex_adversarial_report.json"
SCHEMA = ROOT / "audit" / "schema" / "apex_adversarial_report.schema.json"


def _report() -> dict:
    return json.loads(REPORT.read_text(encoding="utf-8"))


def test_report_validates_against_schema() -> None:
    report = _report()
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    assert report["schema"] == schema["$id"]
    assert len(report["attacks"]) >= 5
    try:
        import jsonschema
    except ImportError:
        return
    jsonschema.validate(report, schema)


def test_every_attack_is_defeated_and_bound_to_a_test() -> None:
    report = _report()
    for attack in report["attacks"]:
        assert attack["defeated"] is True, f"attack not defeated: {attack['id']}"
        node = attack["test"]
        file_part, _, func = node.partition("::")
        path = ROOT / file_part
        assert path.is_file(), f"attack {attack['id']} references missing file: {file_part}"
        assert f"def {func}" in path.read_text(encoding="utf-8"), func


def test_verdict_is_pass_iff_all_defeated() -> None:
    report = _report()
    assert report["verdict"] == (
        "PASS" if all(a["defeated"] for a in report["attacks"]) else "FAIL"
    )
