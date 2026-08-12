# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Closure tests for the DAT-009 evidence-class contamination gate.

Bans synthetic -> empirical label leakage. The canonical evidence classes are
the SSOT ``governance/project_state.yaml`` (GOV-005):
``{FACT, MEASURED, SIMULATION, HYPOTHESIS, RETIRED}``.

NEGATIVE controls (each MUST fail closed, non-zero exit):
  (1) a SIMULATION artifact backing a MEASURED claim   -> exit 1
  (2) an artifact with no evidence_class               -> exit 1 (absence != clearance)
  (3) a SIMULATION artifact in a real-data manifest    -> exit 1

POSITIVE controls (each MUST pass, exit 0):
  * SIMULATION backing a SIMULATION claim
  * SIMULATION backing a HYPOTHESIS claim (weaker)
  * MEASURED backing a MEASURED claim
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
STATE_FILE = ROOT / "governance/project_state.yaml"
CHECK = ROOT / "scripts/ci/check_evidence_class.py"

REQUIRED_EVIDENCE_CLASSES = {"FACT", "MEASURED", "SIMULATION", "HYPOTHESIS", "RETIRED"}


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CHECK), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def _write_manifest(tmp_path: Path, name: str, payload: object) -> Path:
    p = tmp_path / name
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


# --------------------------------------------------------------------------- #
# Ontology binding — the classes this gate enforces are exactly GOV-005's.
# --------------------------------------------------------------------------- #
def test_gate_reads_canonical_classes_from_ssot() -> None:
    data = yaml.safe_load(STATE_FILE.read_text(encoding="utf-8"))
    class_names = {c["name"] for c in data["evidence_classes"]}
    assert class_names == REQUIRED_EVIDENCE_CLASSES


# --------------------------------------------------------------------------- #
# NEGATIVE (1) — SIMULATION backing a MEASURED claim fails closed.
# --------------------------------------------------------------------------- #
def test_negative_simulation_backs_measured(tmp_path: Path) -> None:
    m = _write_manifest(
        tmp_path,
        "contaminated.json",
        [{"id": "art-sim-1", "evidence_class": "SIMULATION", "backs_claim_class": "MEASURED"}],
    )
    result = _run("--manifest", str(m))
    assert result.returncode == 1, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "FLAGGED"
    assert payload["violation_count"] >= 1
    kinds = {v["kind"] for v in payload["violations"]}
    assert "CROSS_CLASS_CONTAMINATION" in kinds


def test_negative_simulation_backs_fact(tmp_path: Path) -> None:
    m = _write_manifest(
        tmp_path,
        "contaminated_fact.json",
        [{"id": "art-sim-2", "evidence_class": "SIMULATION", "backs_claim_class": "FACT"}],
    )
    result = _run("--manifest", str(m))
    assert result.returncode == 1, result.stdout + result.stderr
    assert json.loads(result.stdout)["status"] == "FLAGGED"


# --------------------------------------------------------------------------- #
# NEGATIVE (2) — an artifact with no evidence_class fails closed.
# --------------------------------------------------------------------------- #
def test_negative_missing_class(tmp_path: Path) -> None:
    m = _write_manifest(
        tmp_path,
        "unlabeled.json",
        [{"id": "art-unlabeled", "backs_claim_class": "SIMULATION"}],
    )
    result = _run("--manifest", str(m))
    assert result.returncode == 1, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "FLAGGED"
    assert any(v["kind"] == "MISSING_CLASS" for v in payload["violations"])


def test_negative_empty_class_string(tmp_path: Path) -> None:
    m = _write_manifest(
        tmp_path,
        "blank_class.json",
        [{"id": "art-blank", "evidence_class": ""}],
    )
    result = _run("--manifest", str(m))
    assert result.returncode == 1
    assert any(v["kind"] == "MISSING_CLASS" for v in json.loads(result.stdout)["violations"])


# --------------------------------------------------------------------------- #
# NEGATIVE (3) — SIMULATION in a real-data manifest fails closed.
# --------------------------------------------------------------------------- #
def test_negative_simulation_in_real_data_manifest_flag(tmp_path: Path) -> None:
    m = _write_manifest(
        tmp_path,
        "real_data_flag.json",
        [{"id": "art-real-1", "evidence_class": "SIMULATION"}],
    )
    result = _run("--manifest", str(m), "--real-data")
    assert result.returncode == 1, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "FLAGGED"
    assert any(v["kind"] == "SYNTHETIC_IN_REAL_DATA_MANIFEST" for v in payload["violations"])


def test_negative_simulation_in_real_data_manifest_declared(tmp_path: Path) -> None:
    m = _write_manifest(
        tmp_path,
        "real_data_declared.json",
        {"real_data": True, "records": [{"id": "art-real-2", "evidence_class": "SIMULATION"}]},
    )
    result = _run("--manifest", str(m))
    assert result.returncode == 1, result.stdout + result.stderr
    assert any(
        v["kind"] == "SYNTHETIC_IN_REAL_DATA_MANIFEST"
        for v in json.loads(result.stdout)["violations"]
    )


def test_negative_unknown_class(tmp_path: Path) -> None:
    m = _write_manifest(
        tmp_path,
        "unknown.json",
        [{"id": "art-unknown", "evidence_class": "PROVEN"}],
    )
    result = _run("--manifest", str(m))
    assert result.returncode == 1
    assert any(v["kind"] == "UNKNOWN_CLASS" for v in json.loads(result.stdout)["violations"])


# --------------------------------------------------------------------------- #
# POSITIVE — evidence backing at-or-below its own strength passes.
# --------------------------------------------------------------------------- #
def test_positive_simulation_backs_simulation(tmp_path: Path) -> None:
    m = _write_manifest(
        tmp_path,
        "sim_sim.json",
        [{"id": "art-ok-1", "evidence_class": "SIMULATION", "backs_claim_class": "SIMULATION"}],
    )
    result = _run("--manifest", str(m))
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["status"] == "PASS"


def test_positive_simulation_backs_hypothesis(tmp_path: Path) -> None:
    m = _write_manifest(
        tmp_path,
        "sim_hyp.json",
        [{"id": "art-ok-2", "evidence_class": "SIMULATION", "backs_claim_class": "HYPOTHESIS"}],
    )
    result = _run("--manifest", str(m))
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["violation_count"] == 0


def test_positive_measured_backs_measured(tmp_path: Path) -> None:
    m = _write_manifest(
        tmp_path,
        "meas_meas.json",
        [{"id": "art-ok-3", "evidence_class": "MEASURED", "backs_claim_class": "MEASURED"}],
    )
    result = _run("--manifest", str(m))
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["status"] == "PASS"


def test_positive_measured_in_real_data_manifest(tmp_path: Path) -> None:
    # A MEASURED (empirical) artifact IS allowed in a real-data manifest.
    m = _write_manifest(
        tmp_path,
        "real_ok.json",
        [{"id": "art-ok-4", "evidence_class": "MEASURED", "backs_claim_class": "MEASURED"}],
    )
    result = _run("--manifest", str(m), "--real-data")
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["status"] == "PASS"


def test_every_artifact_displays_its_class(tmp_path: Path) -> None:
    m = _write_manifest(
        tmp_path,
        "mixed.json",
        [
            {"id": "a", "evidence_class": "MEASURED", "backs_claim_class": "MEASURED"},
            {"id": "b", "evidence_class": "SIMULATION", "backs_claim_class": "SIMULATION"},
        ],
    )
    result = _run("--manifest", str(m))
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["artifact_count"] == 2
    ids = {a["id"] for a in payload["artifacts"]}
    assert ids == {"a", "b"}
    # Every listed artifact carries an explicit evidence_class field.
    assert all("evidence_class" in a for a in payload["artifacts"])


# --------------------------------------------------------------------------- #
# Fail-closed structural errors -> exit 2 (tool/ontology broken).
# --------------------------------------------------------------------------- #
def test_missing_manifest_path_errors() -> None:
    result = _run("--manifest", str(ROOT / "does_not_exist_xyz.json"))
    assert result.returncode == 2, result.stdout + result.stderr
    assert json.loads(result.stdout)["status"] == "ERROR"


def test_record_without_id_errors(tmp_path: Path) -> None:
    m = _write_manifest(tmp_path, "no_id.json", [{"evidence_class": "SIMULATION"}])
    result = _run("--manifest", str(m))
    assert result.returncode == 2, result.stdout + result.stderr
    assert json.loads(result.stdout)["status"] == "ERROR"
