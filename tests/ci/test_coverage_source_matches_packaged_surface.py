# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Bind the packaged production surface to the measured coverage surface.

A package that ships in the wheel (``[tool.setuptools.packages.find].include``)
must be measured by some coverage profile OR carry a concrete allowlist reason.
This is the ratchet that fails closed on a NEW shipped-but-uncounted package —
the false-denominator gap the F02 profile work started but did not fully lock.

It complements, not duplicates:
  * ``tests/audit/test_coverage_honesty.py`` — omit ⊄ source *within* a profile;
  * ``tests/test_coverage_threshold_sync.py`` — named 90/98 gate consistency.
This test covers the orthogonal axis: packaged roots ⊆ (measured ∪ allowlisted).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import tools.audit_coverage_surface as acs

ROOT = Path(__file__).resolve().parents[2]
ALLOWLIST = ROOT / "tests" / "fixtures" / "coverage_surface_allowlist.json"
REPORT = ROOT / "artifacts" / "coverage_surface" / "coverage_surface_report.json"
SCHEMA = ROOT / "audit" / "schema" / "coverage_surface_report.schema.json"


def test_report_conforms_to_declared_schema() -> None:
    """No artifact without a schema: the committed report validates against its
    declared JSON Schema (structural floor always; full jsonschema in CI)."""
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    committed = json.loads(REPORT.read_text(encoding="utf-8"))
    # Self-declared id must match the schema file's $id.
    assert committed.get("schema") == schema["$id"], (
        f"report schema id {committed.get('schema')!r} != schema $id {schema['$id']!r}"
    )
    # Structural floor — enforced even without jsonschema installed.
    for key in schema["required"]:
        assert key in committed, f"report missing required key {key!r}"
    assert committed["verdict"] in ("PASS", "FAIL")
    # Full JSON-Schema validation when the optional dep is present (dev/CI).
    try:
        import jsonschema
    except ImportError:
        return
    jsonschema.validate(committed, schema)


def test_no_packaged_production_root_is_unmeasured_and_unallowlisted() -> None:
    """Ratchet: every packaged root is measured or allowlisted; none forbidden."""
    report = acs.audit()
    assert report["forbidden_gaps"] == [], (
        "Coverage surface VIOLATED: packaged production roots ship in the wheel "
        f"but are neither in any coverage profile source nor allowlisted: "
        f"{report['forbidden_gaps']}. Add each to [tool.coverage.run].source / a "
        f"*.coveragerc, or to tests/fixtures/coverage_surface_allowlist.json with "
        f"a concrete reason."
    )
    assert report["invalid_allowlist_entries"] == [], (
        "Coverage surface allowlist VIOLATED: entries with an unknown reason "
        f"category or empty note: {report['invalid_allowlist_entries']}."
    )
    assert report["verdict"] == "PASS"


def test_allowlist_entries_are_honest_and_non_vacuous() -> None:
    """Every allowlist entry must defend a REAL gap with a concrete reason.

    An allowlist that quietly excuses an already-measured or non-packaged root
    is a lie by inclusion — it would let a future gap hide behind a stale entry.
    """
    report = acs.audit()
    allowlist: dict[str, dict[str, str]] = json.loads(ALLOWLIST.read_text(encoding="utf-8"))

    packaged = set(report["packaged_roots"])
    measured = set(report["coverage_sources"])
    allowed = acs.ALLOWED_REASONS

    for root, entry in allowlist.items():
        assert root in packaged, f"allowlist defends non-packaged root {root!r}"
        assert root not in measured, (
            f"allowlist defends already-measured root {root!r} — remove the "
            "stale entry so a real future gap cannot hide behind it."
        )
        assert entry.get("reason") in allowed, (
            f"allowlist root {root!r} has invalid reason {entry.get('reason')!r}; "
            f"allowed: {sorted(allowed)}."
        )
        note = entry.get("note", "").strip()
        assert len(note) >= 20, f"allowlist root {root!r} needs a concrete note, got {note!r}"
        vague = ("later", "optional", "low priority", "todo", "wip")
        assert not any(v in note.lower() for v in vague), (
            f"allowlist root {root!r} note is vague ({note!r}); name the concrete reason."
        )


def test_stale_packaging_roots_are_flagged_not_silent() -> None:
    """A packaged root with no source directory is a packaging defect.

    It must be surfaced (stale_packaging_roots) and explicitly allowlisted with a
    cleanup note, never silently measured-or-ignored.
    """
    report = acs.audit()
    allowlist: dict[str, dict[str, str]] = json.loads(ALLOWLIST.read_text(encoding="utf-8"))
    for root in report["stale_packaging_roots"]:
        assert root in allowlist, (
            f"stale packaged root {root!r} (no source directory) must be "
            "allowlisted with a cleanup note or removed from packaging."
        )


def test_committed_coverage_surface_report_is_fresh() -> None:
    """The committed audit artifact must match a fresh audit (no drift)."""
    if not REPORT.exists():
        pytest.fail(f"missing committed report {REPORT}; run tools/audit_coverage_surface.py --out")
    fresh = acs.audit()
    committed = json.loads(REPORT.read_text(encoding="utf-8"))
    # Compare EVERY field the auditor emits — allowlisted, missing_from_coverage,
    # stale_packaging_roots, coverage_sources_by_profile, invalid_allowlist_entries
    # and measured can drift silently if only the headline four are checked.
    assert set(committed) == set(fresh), (
        f"coverage_surface_report.json key set drifted: "
        f"committed-only={set(committed) - set(fresh)} fresh-only={set(fresh) - set(committed)}"
    )
    for key in fresh:
        assert committed[key] == fresh[key], (
            f"coverage_surface_report.json is stale on {key!r}: "
            f"committed={committed[key]} fresh={fresh[key]}. Regenerate with "
            "python tools/audit_coverage_surface.py --out "
            "artifacts/coverage_surface/coverage_surface_report.json"
        )
