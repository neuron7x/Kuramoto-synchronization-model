# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Witnesses for law_requires_positive_and_negative_witness (governance meta-law)."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest

from core.physics.governance import (
    DEFAULT_CATALOG_PATH,
    check_negative_controls,
    check_threshold_migration,
    check_witness_coverage,
    claim_evidence_map,
    load_catalog,
    promotion_gate,
    validate_law_schema,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _catalog() -> dict[str, Any]:
    return load_catalog(DEFAULT_CATALOG_PATH)


def test_full_catalog_passes_promotion_gate() -> None:
    """Positive witness: the real catalog has full witness+negative-control coverage."""
    catalog = _catalog()
    # Coverage gate (witnesses + negative controls) must be clean; evidence is
    # emitted by the validator step, so it is not required here.
    assert check_witness_coverage(catalog, REPO_ROOT) == []
    assert check_negative_controls(catalog, REPO_ROOT) == []
    gate = promotion_gate(catalog, REPO_ROOT, require_evidence=False)
    assert gate["status"] == "PASS", gate
    assert gate["n_blocking"] == 47


def test_law_without_negative_control_fails_gate() -> None:
    """Negative control: stripping a law's negative control fails the gate."""
    catalog = copy.deepcopy(_catalog())
    catalog["laws"][0]["negative_control"] = "tests/physics/test_ricci_kuramoto.py::does_not_exist"
    assert catalog["laws"][0]["id"] in check_negative_controls(catalog, REPO_ROOT)
    gate = promotion_gate(catalog, REPO_ROOT, require_evidence=False)
    assert gate["status"] == "FAIL"


def test_law_without_test_fails_gate() -> None:
    """A law whose positive witness is not collected fails the gate."""
    catalog = copy.deepcopy(_catalog())
    catalog["laws"][1]["positive_witness"] = "tests/physics/test_ricci_kuramoto.py::missing_fn"
    assert catalog["laws"][1]["id"] in check_witness_coverage(catalog, REPO_ROOT)
    assert promotion_gate(catalog, REPO_ROOT, require_evidence=False)["status"] == "FAIL"


def test_claim_without_evidence_fails_gate() -> None:
    """With evidence required and an evidence path pointing nowhere, the gate fails."""
    catalog = copy.deepcopy(_catalog())
    catalog["laws"][0]["evidence_output"] = "evidence/physics/nonexistent_report.json"
    evidence = claim_evidence_map(catalog, REPO_ROOT)
    assert evidence[catalog["laws"][0]["id"]] is False
    gate = promotion_gate(catalog, REPO_ROOT, require_evidence=True)
    assert gate["status"] == "FAIL"


def test_threshold_change_without_migration_note_fails() -> None:
    """A threshold drift vs baseline without a migration note is flagged."""
    baseline = _catalog()
    changed = copy.deepcopy(baseline)
    changed["laws"][0]["threshold"] = "tol = 1e-3 (relative)"  # silently loosened
    offending = check_threshold_migration(changed, baseline, migration_notes={})
    assert changed["laws"][0]["id"] in offending
    # A documented migration clears it.
    cleared = check_threshold_migration(
        changed, baseline, migration_notes={changed["laws"][0]["id"]: "loosened per audit #X"}
    )
    assert cleared == []


def test_schema_validation_flags_missing_fields() -> None:
    """validate_law_schema reports each missing required field."""
    errors = validate_law_schema({"id": "x"})
    assert any("missing required field 'claim'" in e for e in errors)


def test_review_packet_generation_succeeds(tmp_path: Path) -> None:
    """Review packet generation produces the three docs deterministically."""
    from tools.build_physics_review_packet import build_review_packet
    from tools.validate_physics_contracts import validate

    # Stage a minimal repo tree the tools resolve against.
    (tmp_path / "physics_contracts").mkdir()
    (tmp_path / "physics_contracts" / "falsification_catalog.yaml").write_text(
        (REPO_ROOT / "physics_contracts" / "falsification_catalog.yaml").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )
    # Copy the tests so witness/negative-control coverage resolves under tmp_path.
    (tmp_path / "tests" / "physics").mkdir(parents=True)
    for src in (REPO_ROOT / "tests" / "physics").glob("test_*.py"):
        (tmp_path / "tests" / "physics" / src.name).write_text(
            src.read_text(encoding="utf-8"), encoding="utf-8"
        )

    verdict = validate(tmp_path)
    assert verdict["status"] == "PASS", verdict
    summary = build_review_packet(tmp_path)
    assert summary["status"] == "PASS", summary
    for name in ("PHYSICS_VERDICT.md", "PHYSICS_CLAIMS.md", "PHYSICS_REVIEW_PACKET.md"):
        assert (tmp_path / "docs" / name).is_file()
    # Determinism: a second build is byte-identical.
    first = (tmp_path / "docs" / "PHYSICS_VERDICT.md").read_text(encoding="utf-8")
    build_review_packet(tmp_path)
    assert (tmp_path / "docs" / "PHYSICS_VERDICT.md").read_text(encoding="utf-8") == first
