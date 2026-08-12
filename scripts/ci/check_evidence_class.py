#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Evidence-class contamination gate (DAT-009).

Machine-enforces that *synthetic* evidence can never populate an *empirical*
claim or a real-data manifest — i.e. bans synthetic -> empirical label leakage.

The closed vocabulary of evidence classes is the single source of truth
``governance/project_state.yaml`` (GOV-005):

    FACT (4) > MEASURED (3) > SIMULATION (2) > HYPOTHESIS (1) > RETIRED (0)

``SIMULATION`` is the synthetic / seeded boundary; ``MEASURED`` and ``FACT`` are
empirical. This gate reads a manifest (or a directory of manifests) of artifact
records, each shaped ``{id, evidence_class, backs_claim_class?}``, and fails
closed on any of:

  * CROSS_CLASS_CONTAMINATION — an artifact backs a claim STRONGER than its own
    evidence class (the canonical case: a ``SIMULATION`` artifact backing a
    ``MEASURED``/``FACT`` claim). Strength monotonicity: an artifact of strength
    ``s`` may only back a claim of strength ``<= s``.
  * MISSING_CLASS — a record carries no ``evidence_class``. Absence is never
    empirical clearance; an unlabeled artifact fails closed.
  * UNKNOWN_CLASS — a record's ``evidence_class`` is outside the ontology
    vocabulary. An unrecognised label cannot clear anything.
  * SYNTHETIC_IN_REAL_DATA_MANIFEST — a ``SIMULATION`` artifact appears in a
    manifest declared as real-data.

A manifest is "real-data" when the ``--real-data`` flag is passed, or the
manifest object declares ``real_data: true`` or ``manifest_kind`` in
``{real_data, empirical, measured}``.

Manifest shapes accepted:
  * a JSON list of records, or
  * a JSON object with a ``records`` (or ``artifacts``) list, optionally
    carrying ``real_data`` / ``manifest_kind``.
A directory argument is expanded to every ``*.json`` file it contains.

Fail-closed exit codes (matching scripts/ci/check_state_ontology.py):
  * clean                                          -> 0 (OK)
  * any contamination / missing / unknown class    -> 1 (FLAGGED)
  * unparseable SSOT / manifest, malformed record  -> 2 (ERROR)

Every mode prints a deterministic JSON report to stdout, and every artifact is
listed with its class so nothing passes unlabeled or unseen.

Usage::

    python scripts/ci/check_evidence_class.py --manifest datasets/real_data.json --real-data
    python scripts/ci/check_evidence_class.py --manifest results/
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
STATE_FILE = ROOT / "governance/project_state.yaml"

EXIT_OK = 0
EXIT_FLAGGED = 1
EXIT_ERROR = 2

# Empirical classes — a claim backed by one of these asserts real-world / gate
# evidence. Synthetic evidence may never reach them.
EMPIRICAL_CLASSES = frozenset({"FACT", "MEASURED"})
SYNTHETIC_CLASS = "SIMULATION"
REAL_DATA_KINDS = frozenset({"real_data", "empirical", "measured"})

_RECORD_KEYS = ("records", "artifacts")


class EvidenceClassError(Exception):
    """Raised when the SSOT or a manifest is structurally invalid (fail-closed)."""


def load_class_strengths(path: Path = STATE_FILE) -> dict[str, int]:
    """Read the closed evidence-class vocabulary + strengths from the SSOT.

    Fail-closed on any structural gap so a broken ontology can never silently
    disable the gate.
    """
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:  # pragma: no cover - IO edge
        raise EvidenceClassError(f"cannot read/parse {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise EvidenceClassError(f"{path}: top level must be a mapping")
    classes = raw.get("evidence_classes")
    if not isinstance(classes, list) or not classes:
        raise EvidenceClassError("evidence_classes must be a non-empty list")
    strengths: dict[str, int] = {}
    for c in classes:
        if not isinstance(c, dict) or "name" not in c or "strength" not in c:
            raise EvidenceClassError(f"evidence_classes entry missing name/strength: {c!r}")
        try:
            strengths[str(c["name"])] = int(c["strength"])
        except (TypeError, ValueError) as exc:
            raise EvidenceClassError(f"evidence class {c.get('name')!r} bad strength: {exc}") from exc
    if SYNTHETIC_CLASS not in strengths:
        raise EvidenceClassError(f"ontology missing required synthetic class {SYNTHETIC_CLASS!r}")
    missing = sorted(EMPIRICAL_CLASSES - set(strengths))
    if missing:
        raise EvidenceClassError(f"ontology missing required empirical class(es) {missing}")
    return strengths


def _is_real_data_manifest(obj: Any, cli_real_data: bool) -> bool:
    if cli_real_data:
        return True
    if isinstance(obj, dict):
        if bool(obj.get("real_data")):
            return True
        if str(obj.get("manifest_kind", "")).strip().lower() in REAL_DATA_KINDS:
            return True
    return False


def _extract_records(obj: Any, source: str) -> list[dict[str, Any]]:
    if isinstance(obj, list):
        payload = obj
    elif isinstance(obj, dict):
        payload = None
        for key in _RECORD_KEYS:
            if key in obj:
                payload = obj[key]
                break
        if payload is None:
            raise EvidenceClassError(
                f"{source}: object manifest has no {' / '.join(_RECORD_KEYS)} list"
            )
    else:
        raise EvidenceClassError(f"{source}: manifest must be a list or object, got {type(obj).__name__}")
    if not isinstance(payload, list):
        raise EvidenceClassError(f"{source}: records must be a list")
    records: list[dict[str, Any]] = []
    for i, rec in enumerate(payload):
        if not isinstance(rec, dict):
            raise EvidenceClassError(f"{source}: record #{i} is not an object: {rec!r}")
        if "id" not in rec or not str(rec.get("id", "")).strip():
            raise EvidenceClassError(f"{source}: record #{i} has no id: {rec!r}")
        records.append(rec)
    return records


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvidenceClassError(f"cannot read/parse {path}: {exc}") from exc


def _iter_manifest_files(target: Path) -> list[Path]:
    if target.is_dir():
        return sorted(target.rglob("*.json"))
    if target.is_file():
        return [target]
    raise EvidenceClassError(f"manifest path does not exist: {target}")


def check_records(
    records: list[dict[str, Any]],
    strengths: dict[str, int],
    real_data_manifest: bool,
    manifest_id: str,
) -> list[dict[str, Any]]:
    """Return every violation in ``records`` (empty list == clean)."""
    violations: list[dict[str, Any]] = []
    for rec in records:
        art_id = str(rec["id"])
        cls = rec.get("evidence_class")
        cls = None if cls is None or str(cls).strip() == "" else str(cls)

        # (a) unlabeled -> fail closed (absence is not empirical clearance).
        if cls is None:
            violations.append(
                {
                    "manifest": manifest_id,
                    "id": art_id,
                    "evidence_class": None,
                    "backs_claim_class": rec.get("backs_claim_class"),
                    "kind": "MISSING_CLASS",
                    "reason": "artifact carries no evidence_class; absence is not empirical clearance",
                }
            )
            continue

        # (b) label outside the closed vocabulary -> cannot clear anything.
        if cls not in strengths:
            violations.append(
                {
                    "manifest": manifest_id,
                    "id": art_id,
                    "evidence_class": cls,
                    "backs_claim_class": rec.get("backs_claim_class"),
                    "kind": "UNKNOWN_CLASS",
                    "reason": f"evidence_class {cls!r} is outside the ontology vocabulary {sorted(strengths)}",
                }
            )
            continue

        # (c) synthetic artifact inside a real-data manifest.
        if real_data_manifest and cls == SYNTHETIC_CLASS:
            violations.append(
                {
                    "manifest": manifest_id,
                    "id": art_id,
                    "evidence_class": cls,
                    "backs_claim_class": rec.get("backs_claim_class"),
                    "kind": "SYNTHETIC_IN_REAL_DATA_MANIFEST",
                    "reason": "SIMULATION (synthetic) artifact listed in a real-data manifest",
                }
            )

        # (d) backing a claim stronger than this artifact's own class.
        backs = rec.get("backs_claim_class")
        backs = None if backs is None or str(backs).strip() == "" else str(backs)
        if backs is not None:
            if backs not in strengths:
                violations.append(
                    {
                        "manifest": manifest_id,
                        "id": art_id,
                        "evidence_class": cls,
                        "backs_claim_class": backs,
                        "kind": "UNKNOWN_CLASS",
                        "reason": f"backs_claim_class {backs!r} is outside the ontology vocabulary {sorted(strengths)}",
                    }
                )
            elif strengths[backs] > strengths[cls]:
                empirical = backs in EMPIRICAL_CLASSES
                violations.append(
                    {
                        "manifest": manifest_id,
                        "id": art_id,
                        "evidence_class": cls,
                        "backs_claim_class": backs,
                        "kind": "CROSS_CLASS_CONTAMINATION",
                        "reason": (
                            f"{cls} (strength {strengths[cls]}) may not back a "
                            f"{'empirical ' if empirical else ''}{backs} claim "
                            f"(strength {strengths[backs]})"
                        ),
                    }
                )
    return violations


def audit_report(
    target: Path,
    strengths: dict[str, int],
    cli_real_data: bool,
) -> dict[str, Any]:
    files = _iter_manifest_files(target)
    all_violations: list[dict[str, Any]] = []
    artifacts: list[dict[str, Any]] = []
    for f in files:
        obj = _load_json(f)
        manifest_id = str(f.relative_to(ROOT)) if f.is_relative_to(ROOT) else str(f)
        real_data = _is_real_data_manifest(obj, cli_real_data)
        records = _extract_records(obj, manifest_id)
        for rec in records:
            # Every artifact displays its class (None rendered explicitly).
            artifacts.append(
                {
                    "manifest": manifest_id,
                    "id": str(rec["id"]),
                    "evidence_class": rec.get("evidence_class"),
                    "backs_claim_class": rec.get("backs_claim_class"),
                    "real_data_manifest": real_data,
                }
            )
        all_violations.extend(check_records(records, strengths, real_data, manifest_id))

    all_violations.sort(key=lambda v: (v["manifest"], v["id"], v["kind"]))
    artifacts.sort(key=lambda a: (a["manifest"], a["id"]))
    return {
        "status": "FLAGGED" if all_violations else "PASS",
        "gate": "check_evidence_class",
        "target": str(target.relative_to(ROOT)) if target.is_relative_to(ROOT) else str(target),
        "manifest_count": len(files),
        "artifact_count": len(artifacts),
        "artifacts": artifacts,
        "violations": all_violations,
        "violation_count": len(all_violations),
        "evidence_class_strengths": dict(sorted(strengths.items())),
    }


def _emit(report: dict[str, Any]) -> None:
    print(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evidence-class contamination gate (DAT-009).")
    parser.add_argument(
        "--manifest",
        type=str,
        required=True,
        help="Path to a manifest JSON file or a directory of *.json manifests.",
    )
    parser.add_argument(
        "--real-data",
        action="store_true",
        help="Assert the manifest(s) are real-data manifests (bans any SIMULATION record).",
    )
    parser.add_argument("--state-file", type=str, default=None, help="Override SSOT path.")
    args = parser.parse_args(argv)

    state_path = Path(args.state_file) if args.state_file else STATE_FILE
    try:
        strengths = load_class_strengths(state_path)
        report = audit_report(Path(args.manifest), strengths, args.real_data)
    except EvidenceClassError as exc:
        _emit({"status": "ERROR", "gate": "check_evidence_class", "error": str(exc)})
        return EXIT_ERROR

    _emit(report)
    return EXIT_FLAGGED if report["violation_count"] else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
