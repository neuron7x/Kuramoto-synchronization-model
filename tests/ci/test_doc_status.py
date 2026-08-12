# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Closure tests for the DOC-003 doc-status gate.

Mandated cases:
  POSITIVE — the tagged authoritative doc set is consistent with the project
             state (RESEARCH_ALPHA); the gate exits 0.
  NEGATIVE — a synthetic front-matter fixture marked ``status: current`` that
             claims PRODUCTION / production-ready is flagged non-zero.

Plus structural coverage: schema fail-closed, historical/aspirational docs are
not scanned, the use/mention carve-outs, and the report enumeration.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GATE = ROOT / "scripts/ci/check_doc_status.py"


def _load_gate_module():
    spec = importlib.util.spec_from_file_location("check_doc_status", GATE)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


mod = _load_gate_module()


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(GATE), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


# --------------------------------------------------------------------------- #
# POSITIVE — the real tagged set is consistent with RESEARCH_ALPHA.
# --------------------------------------------------------------------------- #
def test_positive_tagged_set_passes() -> None:
    result = _run("--no-write")
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "PASS"
    assert payload["contradiction_count"] == 0
    # The report enumerates every governed doc and its status.
    assert payload["doc_count"] == len(mod.TAGGED_DOCS)
    counts = payload["counts_by_status"]
    assert counts["current"] >= 1
    assert counts["historical"] >= 1
    assert counts["aspirational"] >= 1


def test_report_artifact_is_written(tmp_path: Path) -> None:
    out = tmp_path / "doc_status_report.json"
    result = _run("--report", str(out))
    assert result.returncode == 0, result.stdout + result.stderr
    assert out.exists()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["current_state"] == "RESEARCH_ALPHA"
    assert {d["path"] for d in data["docs"]} == set(mod.TAGGED_DOCS)


def test_every_tagged_doc_has_valid_frontmatter() -> None:
    state = mod.load_state()
    patterns = mod._forbidden_patterns(state)
    for rel in mod.TAGGED_DOCS:
        record = mod.evaluate_doc(ROOT / rel, state, patterns, rel=rel)
        assert record["status"] in mod.VALID_STATUSES
        assert record["authoritative_for"]


# --------------------------------------------------------------------------- #
# NEGATIVE — a current doc claiming PRODUCTION is flagged.
# --------------------------------------------------------------------------- #
_CURRENT_PRODUCTION_FIXTURE = """---
doc_status:
  status: current
  authoritative_for:
    - synthetic_fixture
  valid_from: 2026-07-19
---

# Synthetic Fixture

This system is production-ready and has been validated on live venues.
"""


def test_negative_current_claiming_production_is_flagged(tmp_path: Path) -> None:
    doc = tmp_path / "bad_current.md"
    doc.write_text(_CURRENT_PRODUCTION_FIXTURE, encoding="utf-8")
    result = _run("--doc", str(doc), "--no-write")
    assert result.returncode == 1, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "FLAGGED"
    assert payload["contradiction_count"] >= 1
    claims = {c["claim"] for d in payload["docs"] for c in d["contradictions"]}
    assert "production-ready" in claims
    assert "validated" in claims


def test_negative_via_evaluate_doc(tmp_path: Path) -> None:
    doc = tmp_path / "bad_current.md"
    doc.write_text(_CURRENT_PRODUCTION_FIXTURE, encoding="utf-8")
    state = mod.load_state()
    patterns = mod._forbidden_patterns(state)
    record = mod.evaluate_doc(doc, state, patterns)
    assert record["scanned"] is True
    assert record["contradictions"]
    assert all(c["current_state"] == "RESEARCH_ALPHA" for c in record["contradictions"])


# --------------------------------------------------------------------------- #
# Historical / aspirational docs are NOT scanned (past/future claims allowed).
# --------------------------------------------------------------------------- #
def test_historical_doc_with_past_claim_is_not_flagged(tmp_path: Path) -> None:
    doc = tmp_path / "old.md"
    doc.write_text(
        "---\n"
        "doc_status:\n"
        "  status: historical\n"
        "  authoritative_for: [old_snapshot]\n"
        "  valid_from: 2025-12-19\n"
        "  valid_to: 2026-07-16\n"
        "  superseded_by: governance/project_state.yaml\n"
        "---\n\n"
        "# Old\n\nThe core engine is production-ready and validated.\n",
        encoding="utf-8",
    )
    state = mod.load_state()
    patterns = mod._forbidden_patterns(state)
    record = mod.evaluate_doc(doc, state, patterns)
    assert record["status"] == "historical"
    assert record["scanned"] is False
    assert record["contradictions"] == []


def test_aspirational_doc_is_not_scanned(tmp_path: Path) -> None:
    doc = tmp_path / "future.md"
    doc.write_text(
        "---\n"
        "doc_status:\n"
        "  status: aspirational\n"
        "  authoritative_for: [target]\n"
        "  valid_from: 2026-07-19\n"
        "---\n\n"
        "# Target\n\nOne day GeoSync will be production-ready.\n",
        encoding="utf-8",
    )
    state = mod.load_state()
    patterns = mod._forbidden_patterns(state)
    record = mod.evaluate_doc(doc, state, patterns)
    assert record["scanned"] is False
    assert record["contradictions"] == []


# --------------------------------------------------------------------------- #
# Use / mention carve-outs.
# --------------------------------------------------------------------------- #
def test_claim_word_in_code_fence_is_not_flagged(tmp_path: Path) -> None:
    doc = tmp_path / "code.md"
    doc.write_text(
        "---\n"
        "doc_status:\n"
        "  status: current\n"
        "  authoritative_for: [x]\n"
        "  valid_from: 2026-07-19\n"
        "---\n\n"
        "# X\n\nRun this:\n\n```\ncheck --text 'production-ready'\n```\n",
        encoding="utf-8",
    )
    state = mod.load_state()
    patterns = mod._forbidden_patterns(state)
    record = mod.evaluate_doc(doc, state, patterns)
    assert record["contradictions"] == []


def test_mention_marker_exempts_and_is_counted(tmp_path: Path) -> None:
    doc = tmp_path / "mention.md"
    doc.write_text(
        "---\n"
        "doc_status:\n"
        "  status: current\n"
        "  authoritative_for: [x]\n"
        "  valid_from: 2026-07-19\n"
        "---\n\n"
        "# X\n\n"
        'The word "validated" is forbidden here. <!-- doc-status:claim-mention -->\n',
        encoding="utf-8",
    )
    state = mod.load_state()
    patterns = mod._forbidden_patterns(state)
    record = mod.evaluate_doc(doc, state, patterns)
    assert record["contradictions"] == []
    assert record["mention_exemptions"] == 1


def test_defines_vocabulary_doc_is_recorded_not_scanned(tmp_path: Path) -> None:
    doc = tmp_path / "vocab.md"
    doc.write_text(
        "---\n"
        "doc_status:\n"
        "  status: current\n"
        "  authoritative_for: [firewall]\n"
        "  valid_from: 2026-07-19\n"
        "  defines_claim_vocabulary: true\n"
        "---\n\n"
        '# Firewall\n\nForbidden words: validated, proven, production-ready.\n',
        encoding="utf-8",
    )
    state = mod.load_state()
    patterns = mod._forbidden_patterns(state)
    record = mod.evaluate_doc(doc, state, patterns)
    assert record["defines_claim_vocabulary"] is True
    assert record["scanned"] is False
    assert record["contradictions"] == []


# --------------------------------------------------------------------------- #
# Structural fail-closed.
# --------------------------------------------------------------------------- #
def test_missing_front_matter_fails_closed(tmp_path: Path) -> None:
    doc = tmp_path / "nofm.md"
    doc.write_text("# No front matter here\n", encoding="utf-8")
    result = _run("--doc", str(doc), "--no-write")
    assert result.returncode == 2, result.stdout + result.stderr
    assert json.loads(result.stdout)["status"] == "ERROR"


def test_bad_status_enum_fails_closed(tmp_path: Path) -> None:
    doc = tmp_path / "bad.md"
    doc.write_text(
        "---\ndoc_status:\n  status: shipped\n  authoritative_for: [x]\n"
        "  valid_from: 2026-07-19\n---\n\n# X\n",
        encoding="utf-8",
    )
    state = mod.load_state()
    patterns = mod._forbidden_patterns(state)
    with pytest.raises(mod.DocStatusError):
        mod.evaluate_doc(doc, state, patterns)


def test_historical_without_supersession_fails_closed(tmp_path: Path) -> None:
    doc = tmp_path / "h.md"
    doc.write_text(
        "---\ndoc_status:\n  status: historical\n  authoritative_for: [x]\n"
        "  valid_from: 2025-01-01\n---\n\n# X\n",
        encoding="utf-8",
    )
    state = mod.load_state()
    patterns = mod._forbidden_patterns(state)
    with pytest.raises(mod.DocStatusError):
        mod.evaluate_doc(doc, state, patterns)


def test_empty_authoritative_for_fails_closed(tmp_path: Path) -> None:
    doc = tmp_path / "e.md"
    doc.write_text(
        "---\ndoc_status:\n  status: current\n  authoritative_for: []\n"
        "  valid_from: 2026-07-19\n---\n\n# X\n",
        encoding="utf-8",
    )
    state = mod.load_state()
    patterns = mod._forbidden_patterns(state)
    with pytest.raises(mod.DocStatusError):
        mod.evaluate_doc(doc, state, patterns)


def test_bad_valid_from_date_fails_closed(tmp_path: Path) -> None:
    doc = tmp_path / "d.md"
    doc.write_text(
        "---\ndoc_status:\n  status: current\n  authoritative_for: [x]\n"
        "  valid_from: not-a-date\n---\n\n# X\n",
        encoding="utf-8",
    )
    state = mod.load_state()
    patterns = mod._forbidden_patterns(state)
    with pytest.raises(mod.DocStatusError):
        mod.evaluate_doc(doc, state, patterns)
