# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Closure tests for the GOV-005 project-state ontology.

Covers the three mandated cases:
  (1) the SSOT parses and every declared enum value is defined + reachable;
  (2) POSITIVE — a claim word with a valid backing evidence class passes;
  (3) NEGATIVE — a claim word with no / wrong backing class is flagged.

Plus single-source-generation proof: the status surface is rendered FROM the
SSOT (values that live only in the state file appear in the generated output),
and the required maturity states / evidence classes are exactly the ontology
GOV-005 mandates.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
STATE_FILE = ROOT / "governance/project_state.yaml"
CHECK = ROOT / "scripts/ci/check_state_ontology.py"
GEN = ROOT / "scripts/ci/gen_status_surfaces.py"

REQUIRED_MATURITY_STATES = {
    "RESEARCH_ALPHA",
    "REPEATABLE",
    "REPRODUCIBLE",
    "REPLICATED",
    "RELEASE_CANDIDATE",
    "PRODUCTION",
}
REQUIRED_EVIDENCE_CLASSES = {"FACT", "MEASURED", "SIMULATION", "HYPOTHESIS", "RETIRED"}


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


# --------------------------------------------------------------------------- #
# (1) SSOT parses and every enum value is defined.
# --------------------------------------------------------------------------- #
def test_state_file_parses_and_enums_defined() -> None:
    data = yaml.safe_load(STATE_FILE.read_text(encoding="utf-8"))
    assert isinstance(data, dict)

    state_names = {s["name"] for s in data["maturity_states"]}
    class_names = {c["name"] for c in data["evidence_classes"]}

    # The mandated ontology, exactly.
    assert state_names == REQUIRED_MATURITY_STATES
    assert class_names == REQUIRED_EVIDENCE_CLASSES

    # current_state is a defined state.
    assert data["current_state"] in state_names

    # Every forbidden-claim requirement references a defined evidence class.
    for entry in data["forbidden_claims"]:
        assert entry["requires"], f"{entry['claim']} has empty requires"
        for cls in entry["requires"]:
            assert cls in class_names, f"{entry['claim']} requires undefined class {cls}"

    # Ranks form a contiguous ladder 0..n-1.
    ranks = sorted(s["rank"] for s in data["maturity_states"])
    assert ranks == list(range(len(ranks)))


def test_validate_gate_passes() -> None:
    result = _run(str(CHECK), "--validate")
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "PASS"
    assert set(payload["maturity_states"]) == REQUIRED_MATURITY_STATES
    assert set(payload["evidence_classes"]) == REQUIRED_EVIDENCE_CLASSES


# --------------------------------------------------------------------------- #
# (2) POSITIVE — valid backing evidence class passes.
# --------------------------------------------------------------------------- #
def test_positive_validated_with_measured_passes() -> None:
    result = _run(str(CHECK), "--check-text", "the pipeline result is validated", "--evidence-class", "MEASURED")
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "PASS"
    assert payload["contradiction_count"] == 0


def test_positive_proven_with_fact_passes() -> None:
    result = _run(str(CHECK), "--check-text", "the invariant count is proven by the gate", "--evidence-class", "FACT")
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["status"] == "PASS"


def test_positive_clean_text_passes() -> None:
    result = _run(str(CHECK), "--check-text", "a synthetic descriptor of seeded inputs", "--evidence-class", "SIMULATION")
    assert result.returncode == 0
    assert json.loads(result.stdout)["contradiction_count"] == 0


# --------------------------------------------------------------------------- #
# (3) NEGATIVE — claim word with no / wrong backing class is flagged.
# --------------------------------------------------------------------------- #
def test_negative_validated_without_class_flagged() -> None:
    result = _run(str(CHECK), "--check-text", "our alpha is validated")
    assert result.returncode == 1, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "FLAGGED"
    assert payload["contradiction_count"] >= 1
    assert any(c["claim"] == "validated" for c in payload["contradictions"])


def test_negative_production_grade_with_hypothesis_flagged() -> None:
    result = _run(str(CHECK), "--check-text", "this is production-grade", "--evidence-class", "HYPOTHESIS")
    assert result.returncode == 1, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "FLAGGED"
    assert any(c["claim"] == "production-grade" for c in payload["contradictions"])


def test_negative_simulation_cannot_back_validated() -> None:
    # SIMULATION (synthetic) may never back "validated" — the core anti-pattern.
    result = _run(str(CHECK), "--check-text", "validated on synthetic data", "--evidence-class", "SIMULATION")
    assert result.returncode == 1
    assert json.loads(result.stdout)["status"] == "FLAGGED"


def test_unknown_evidence_class_fails_closed() -> None:
    result = _run(str(CHECK), "--check-text", "anything", "--evidence-class", "NONSENSE")
    assert result.returncode == 2, result.stdout + result.stderr
    assert json.loads(result.stdout)["status"] == "ERROR"


# --------------------------------------------------------------------------- #
# Single-source-generation proof.
# --------------------------------------------------------------------------- #
def test_status_surface_is_generated_from_ssot() -> None:
    data = yaml.safe_load(STATE_FILE.read_text(encoding="utf-8"))
    result = _run(str(GEN))
    assert result.returncode == 0, result.stderr
    out = result.stdout
    # The current state and the generator provenance banner must appear.
    assert data["current_state"] in out
    assert "gen_status_surfaces.py" in out
    # Every maturity state and evidence class flows through from the SSOT.
    for s in data["maturity_states"]:
        assert s["name"] in out
    for c in data["evidence_classes"]:
        assert c["name"] in out
    # A forbidden claim word appears in the rendered firewall table.
    assert data["forbidden_claims"][0]["claim"] in out


def test_badge_reflects_current_state() -> None:
    data = yaml.safe_load(STATE_FILE.read_text(encoding="utf-8"))
    result = _run(str(GEN), "--format", "badge")
    assert result.returncode == 0, result.stderr
    assert data["current_state"] in result.stdout


# --------------------------------------------------------------------------- #
# Destroyer regression DS-02: homoglyph / zero-width / NUL evasion of the claim
# firewall. Each evasive spelling of "validated" must still be flagged, while a
# clean benign term still passes (non-vacuous twin).
# --------------------------------------------------------------------------- #
def test_ds02_cyrillic_homoglyph_validated_flagged() -> None:
    # Cyrillic 'а' (U+0430) swapped for Latin 'a'.
    result = _run(str(CHECK), "--check-text", "our alpha is vаlidаted")
    assert result.returncode == 1, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "FLAGGED"
    assert any(c["claim"] == "validated" for c in payload["contradictions"])


def test_ds02_zero_width_space_validated_flagged() -> None:
    # ZWSP (U+200B) spliced inside the word.
    result = _run(str(CHECK), "--check-text", "our alpha is valid​ated")
    assert result.returncode == 1, result.stdout + result.stderr
    assert json.loads(result.stdout)["status"] == "FLAGGED"


def test_ds02_nul_byte_validated_flagged(tmp_path: Path) -> None:
    # NUL cannot survive an argv, so exercise it via --check-file.
    f = tmp_path / "nul.txt"
    f.write_bytes(b"our alpha is valid\x00ated\n")
    result = _run(str(CHECK), "--check-file", str(f))
    assert result.returncode == 1, result.stdout + result.stderr
    assert json.loads(result.stdout)["status"] == "FLAGGED"


def test_ds02_ascii_validated_still_flagged() -> None:
    # Non-vacuous twin: the plain ASCII form is still caught (no over/under-fold).
    result = _run(str(CHECK), "--check-text", "our alpha is validated")
    assert result.returncode == 1, result.stdout + result.stderr
    assert json.loads(result.stdout)["status"] == "FLAGGED"


def test_ds02_clean_term_still_passes() -> None:
    # Benign twin: normalization must not manufacture a false positive.
    result = _run(str(CHECK), "--check-text", "a synthetic descriptor", "--evidence-class", "SIMULATION")
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["contradiction_count"] == 0
