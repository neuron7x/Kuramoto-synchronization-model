# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Closure tests for the RES-003 operational-definition terminology gate.

POSITIVE:
  * the committed ontology validates against the schema + semantic rules (rc 0);
  * asserting a genuine mechanism term as a mechanism is supported;
  * the honest labelling holds: the neuromodulator terms are ANALOGUE, and the
    metaphor-only terms are never mechanism.

NEGATIVE (each must go RED):
  * a mechanism term missing a falsifier;
  * a term labelled mechanism with no observable_mapping;
  * a term with an unknown status;
  * a metaphor-only term (serotonin) relabelled mechanism;
  * asserting an analogue / unknown term as a mechanism (the claim gate).
"""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[2]
ONTOLOGY = ROOT / "governance/operational_definitions.json"
SCHEMA = ROOT / "schemas/operational_definition.schema.json"
CHECK = ROOT / "scripts/ci/check_terminology.py"

REQUIRED_ACTIVE_TERMS = {
    "synchronization",
    "curvature",
    "energy",
    "entropy",
    "phase_transition",
    "criticality",
}
NEUROMODULATOR_ANALOGUES = {"serotonin", "dopamine", "gaba"}


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def _ontology() -> dict:
    return json.loads(ONTOLOGY.read_text(encoding="utf-8"))


def _write_tmp(tmp_path: Path, data: dict) -> Path:
    p = tmp_path / "ontology.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def _term(data: dict, name: str) -> dict:
    for t in data["terms"]:
        if t["name"] == name:
            return t
    raise KeyError(name)


# --------------------------------------------------------------------------- #
# POSITIVE
# --------------------------------------------------------------------------- #
def test_committed_ontology_is_schema_valid() -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.validate(_ontology(), schema)


def test_validate_gate_passes_on_committed_ontology() -> None:
    result = _run(str(CHECK), "--validate")
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "PASS"
    assert payload["issue_count"] == 0
    # Every required active term is present.
    assert REQUIRED_ACTIVE_TERMS <= set(payload["terms"])


def test_required_active_terms_are_mechanisms_with_full_mapping() -> None:
    data = _ontology()
    for name in REQUIRED_ACTIVE_TERMS:
        term = _term(data, name)
        assert term["status"] == "mechanism", name
        assert term["is_claim"] is True, name
        assert term["math_object"].strip(), name
        assert term["observable_mapping"].strip(), name
        assert term["falsifier"].strip(), name
        assert any(a.strip() for a in term["alternatives"]), name
        assert term["units"].strip(), name
        assert term["validity_domain"].strip(), name


def test_neuromodulators_are_analogue_not_mechanism() -> None:
    data = _ontology()
    metaphor_only = set(data.get("metaphor_only", []))
    for name in NEUROMODULATOR_ANALOGUES:
        term = _term(data, name)
        assert term["status"] == "analogue", f"{name} must be ANALOGUE, not mechanism"
        assert term["is_claim"] is False, name
        assert term["note"].strip(), name
        assert name in metaphor_only, f"{name} must be listed in metaphor_only"


def test_retired_term_is_a_non_claim_tombstone() -> None:
    term = _term(_ontology(), "heisenberg_uncertainty")
    assert term["status"] == "retired"
    assert term["is_claim"] is False
    assert term["note"].strip()
    assert term.get("superseded_by")


def test_assert_mechanism_term_is_supported() -> None:
    result = _run(str(CHECK), "--assert", "synchronization", "--as", "mechanism")
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["status"] == "PASS"


# --------------------------------------------------------------------------- #
# NEGATIVE — each mutation must drive the gate RED.
# --------------------------------------------------------------------------- #
def test_negative_mechanism_missing_falsifier_is_red(tmp_path: Path) -> None:
    data = copy.deepcopy(_ontology())
    _term(data, "synchronization")["falsifier"] = ""
    bad = _write_tmp(tmp_path, data)
    result = _run(str(CHECK), "--validate", "--file", str(bad))
    assert result.returncode == 1, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "FLAGGED"
    assert any("falsifier" in i for i in payload["issues"])


def test_negative_mechanism_missing_observable_mapping_is_red(tmp_path: Path) -> None:
    data = copy.deepcopy(_ontology())
    _term(data, "curvature")["observable_mapping"] = ""
    bad = _write_tmp(tmp_path, data)
    result = _run(str(CHECK), "--validate", "--file", str(bad))
    assert result.returncode == 1, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "FLAGGED"
    assert any("observable_mapping" in i for i in payload["issues"])


def test_negative_unknown_status_is_red(tmp_path: Path) -> None:
    data = copy.deepcopy(_ontology())
    _term(data, "energy")["status"] = "vibes"
    bad = _write_tmp(tmp_path, data)
    result = _run(str(CHECK), "--validate", "--file", str(bad))
    assert result.returncode == 1, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "FLAGGED"
    assert any("unknown status" in i for i in payload["issues"])


def test_negative_metaphor_relabelled_mechanism_is_red(tmp_path: Path) -> None:
    # Relabelling a neuromodulator analogue as a mechanism must fail closed.
    data = copy.deepcopy(_ontology())
    term = _term(data, "serotonin")
    term["status"] = "mechanism"
    term["is_claim"] = True
    bad = _write_tmp(tmp_path, data)
    result = _run(str(CHECK), "--validate", "--file", str(bad))
    assert result.returncode == 1, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "FLAGGED"
    assert any("metaphor-only" in i for i in payload["issues"])


def test_negative_missing_alternatives_is_red(tmp_path: Path) -> None:
    data = copy.deepcopy(_ontology())
    _term(data, "phase_transition")["alternatives"] = []
    bad = _write_tmp(tmp_path, data)
    result = _run(str(CHECK), "--validate", "--file", str(bad))
    assert result.returncode == 1, result.stdout + result.stderr
    assert any("alternative" in i for i in json.loads(result.stdout)["issues"])


def test_claim_gate_flags_analogue_asserted_as_mechanism() -> None:
    result = _run(str(CHECK), "--assert", "dopamine", "--as", "mechanism")
    assert result.returncode == 1, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "FLAGGED"
    assert payload["defined_status"] == "analogue"


def test_claim_gate_flags_undefined_term_asserted_as_mechanism() -> None:
    result = _run(str(CHECK), "--assert", "quantum_alpha", "--as", "mechanism")
    assert result.returncode == 1, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "FLAGGED"
    assert any("no operational definition" in c for c in payload["contradictions"])


def test_claim_gate_flags_retired_term_asserted_as_mechanism() -> None:
    result = _run(str(CHECK), "--assert", "heisenberg_uncertainty", "--as", "mechanism")
    assert result.returncode == 1, result.stdout + result.stderr
    assert json.loads(result.stdout)["defined_status"] == "retired"


# --------------------------------------------------------------------------- #
# Destroyer regression DS-02: a term name carrying a Cyrillic homoglyph / ZWSP
# must resolve to its real ontology entry (and be judged on that entry), not read
# as "undefined". The claim still goes RED; the resolution is proven by
# defined_status matching the real entry (analogue), which is None without folding.
# --------------------------------------------------------------------------- #
def test_ds02_homoglyph_analogue_resolves_and_is_flagged() -> None:
    # Cyrillic 'ѕ' (U+0455) in place of Latin 's' in "serotonin".
    result = _run(str(CHECK), "--assert", "ѕerotonin", "--as", "mechanism")
    assert result.returncode == 1, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "FLAGGED"
    # Proof the fold resolved to the real entry rather than "undefined".
    assert payload["defined_status"] == "analogue"


def test_ds02_zero_width_analogue_resolves_and_is_flagged() -> None:
    result = _run(str(CHECK), "--assert", "sero​tonin", "--as", "mechanism")
    assert result.returncode == 1, result.stdout + result.stderr
    assert json.loads(result.stdout)["defined_status"] == "analogue"


def test_ds02_ascii_analogue_still_flagged() -> None:
    # Non-vacuous twin: plain ASCII resolves and flags identically.
    result = _run(str(CHECK), "--assert", "serotonin", "--as", "mechanism")
    assert result.returncode == 1, result.stdout + result.stderr
    assert json.loads(result.stdout)["defined_status"] == "analogue"


def test_ds02_clean_mechanism_still_supported() -> None:
    # Benign twin: normalization must not break a legitimate mechanism assertion.
    result = _run(str(CHECK), "--assert", "synchronization", "--as", "mechanism")
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["status"] == "PASS"
