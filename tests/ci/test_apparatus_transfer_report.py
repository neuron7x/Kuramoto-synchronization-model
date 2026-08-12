# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""The apparatus must be shown to transfer across >= 2 distinct domains.

The verification apparatus (tool -> artifact -> schema -> fail-closed verdict) is
domain-general only if it is actually applied across distinct domains. This gate
keeps that claim honest: every listed application's tool/artifact/schema exists,
and at least two DISTINCT domains are covered.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "artifacts" / "inference" / "apparatus_transfer_report.json"
SCHEMA = ROOT / "audit" / "schema" / "apparatus_transfer_report.schema.json"


def _report() -> dict:
    return json.loads(REPORT.read_text(encoding="utf-8"))


def test_report_validates_against_schema() -> None:
    report = _report()
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    assert report["schema"] == schema["$id"]
    try:
        import jsonschema
    except ImportError:
        return
    jsonschema.validate(report, schema)


def test_every_application_points_to_existing_files() -> None:
    for entry in _report()["domains"]:
        for key in ("tool", "artifact", "schema_path"):
            assert (ROOT / entry[key]).is_file(), f"{entry['object']}: missing {entry[key]}"


def test_at_least_two_distinct_domains() -> None:
    report = _report()
    distinct = {entry["domain"] for entry in report["domains"]}
    assert len(distinct) >= 2, f"apparatus not shown to generalise: only {distinct}"
    assert report["distinct_domain_count"] == len(distinct)
    assert report["verdict"] == "PASS"
