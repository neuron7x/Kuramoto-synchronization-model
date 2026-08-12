# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for the CITATION.cff forbidden-claim gate (REL-009).

POSITIVE: the cleaned repository CITATION.cff scans to 0 violations (exit 0).
NEGATIVE: a fixture CFF asserting "production-grade market intelligence
platform" is flagged (violation_count > 0, exit 1).

Plus firewall-sourcing, use/mention awareness, and fail-closed behaviour.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
REPO_CFF = ROOT / "CITATION.cff"
STATE_FILE = ROOT / "governance/project_state.yaml"


def _load_gate():
    # Load the target by path — tests/ci helper tests are intentionally
    # independent of repo-level sys.path bootstrapping (see tests/ci/pytest.ini).
    src = ROOT / "scripts/ci/check_cff_claims.py"
    spec = importlib.util.spec_from_file_location("check_cff_claims", src)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gate = _load_gate()

_VALID_HEADER = (
    'cff-version: 1.2.0\n'
    'message: "cite it"\n'
    "type: software\n"
    "authors:\n"
    "  - family-names: Vasylenko\n"
    "    given-names: Yaroslav\n"
)


def _write_cff(tmp_path: Path, *, title: str, abstract: str, keywords: list[str]) -> Path:
    kw = "".join(f"  - {k}\n" for k in keywords)
    text = (
        _VALID_HEADER
        + f'title: "{title}"\n'
        + f"abstract: >-\n  {abstract}\n"
        + "keywords:\n"
        + kw
    )
    path = tmp_path / "CITATION.cff"
    path.write_text(text, encoding="utf-8")
    return path


# --------------------------------------------------------------------------- #
# POSITIVE: real repo CFF is clean.
# --------------------------------------------------------------------------- #
def test_positive_repo_cff_zero_violations() -> None:
    rc = gate.main(["--cff", str(REPO_CFF)])
    assert rc == gate.EXIT_OK

    firewall = gate.load_forbidden_claims(STATE_FILE)
    report = gate.scan_cff(gate.load_cff(REPO_CFF), firewall)
    assert report["status"] == "PASS"
    assert report["violation_count"] == 0, report["violations"]


# --------------------------------------------------------------------------- #
# NEGATIVE: an overclaiming fixture CFF is flagged.
# --------------------------------------------------------------------------- #
def test_negative_production_grade_platform_flagged(tmp_path: Path) -> None:
    bad = _write_cff(
        tmp_path,
        title="GeoSync: production-grade market intelligence platform",
        abstract="A production-grade market intelligence platform for live trading.",
        keywords=["algorithmic-trading"],
    )
    rc = gate.main(["--cff", str(bad)])
    assert rc == gate.EXIT_FLAGGED

    firewall = gate.load_forbidden_claims(STATE_FILE)
    report = gate.scan_cff(gate.load_cff(bad), firewall)
    assert report["status"] == "FLAGGED"
    assert report["violation_count"] > 0
    claims = {v["claim"] for v in report["violations"]}
    assert "production-grade" in claims
    # It was asserted (used), so caught in title AND abstract.
    fields = {v["field"] for v in report["violations"]}
    assert {"title", "abstract"} <= fields


# --------------------------------------------------------------------------- #
# Use / mention awareness: a negated disclaimer is a mention, not a violation.
# --------------------------------------------------------------------------- #
def test_mention_in_disclaimer_not_flagged(tmp_path: Path) -> None:
    ok = _write_cff(
        tmp_path,
        title="GeoSync: verification-first research platform",
        abstract="GeoSync is not a production-grade product and asserts no risk-free edge.",
        keywords=["verification-first"],
    )
    rc = gate.main(["--cff", str(ok)])
    assert rc == gate.EXIT_OK

    firewall = gate.load_forbidden_claims(STATE_FILE)
    report = gate.scan_cff(gate.load_cff(ok), firewall)
    assert report["violation_count"] == 0
    # The disclaimed words are recorded as mentions, not lost.
    mentioned = {m["claim"] for m in report["mentions"]}
    assert {"production-grade", "risk-free"} <= mentioned


# --------------------------------------------------------------------------- #
# Firewall is sourced from the SSOT.
# --------------------------------------------------------------------------- #
def test_firewall_sourced_from_ssot() -> None:
    firewall = gate.load_forbidden_claims(STATE_FILE)
    claims = {e["claim"] for e in firewall}
    assert {"production-grade", "validated", "proven", "risk-free"} <= claims


# --------------------------------------------------------------------------- #
# Fail-closed: unparseable / empty SSOT -> error exit.
# --------------------------------------------------------------------------- #
def test_fail_closed_on_empty_firewall(tmp_path: Path) -> None:
    empty = tmp_path / "state.yaml"
    empty.write_text("forbidden_claims: []\n", encoding="utf-8")
    with pytest.raises(gate.CffClaimError):
        gate.load_forbidden_claims(empty)


def test_fail_closed_on_missing_ssot(tmp_path: Path) -> None:
    missing = tmp_path / "nope.yaml"
    rc = gate.main(["--cff", str(REPO_CFF), "--state-file", str(missing)])
    assert rc == gate.EXIT_ERROR


# --------------------------------------------------------------------------- #
# Report writing.
# --------------------------------------------------------------------------- #
def test_report_written_to_disk(tmp_path: Path) -> None:
    out = tmp_path / "sub" / "report.json"
    gate.main(["--cff", str(REPO_CFF), "--report", str(out)])
    assert out.exists()
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["status"] == "PASS"
    assert payload["scanned_fields"] == ["title", "abstract", "keywords"]
