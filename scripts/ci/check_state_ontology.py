#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Claim-boundary gate over the project-state ontology (GOV-005).

Reads the single source of truth ``governance/project_state.yaml`` and enforces
two things, fail-closed:

1. ``--validate`` — the ontology is internally consistent: every maturity
   state has a rank + definition, ranks are the contiguous sequence
   ``0..n-1``, ``current_state`` is a defined state, every evidence class is
   defined, and every ``requires`` token in the forbidden-claim map is a
   defined evidence class. Any gap exits non-zero.

2. ``--check-text`` / ``--check-file`` — the claim firewall: given text and a
   *declared* evidence class, flag every forbidden claim word whose declared
   class is not one of its ``requires`` classes. A forbidden word used with
   NO declared class (``--evidence-class`` omitted) is always a contradiction:
   a status word with no backing evidence is exactly what this gate exists to
   catch.

Fail-closed rules:
  * a malformed / unparseable state file  -> exit 2 (error)
  * an ``--evidence-class`` outside the ontology vocabulary -> exit 2 (error)
  * any contradiction found               -> exit 1 (flagged)
  * clean                                 -> exit 0

All modes print a deterministic JSON report to stdout.

Usage::

    python scripts/ci/check_state_ontology.py --validate
    python scripts/ci/check_state_ontology.py --check-text "result is validated" \
        --evidence-class MEASURED
    python scripts/ci/check_state_ontology.py --check-file README.md \
        --evidence-class HYPOTHESIS
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ModuleNotFoundError as exc:  # DS-18: fail cleanly, never raw traceback
    print(json.dumps({"status": "ERROR", "error": f"missing dependency: {exc.name}"}))
    sys.exit(2)

# Confusable/zero-width normalization so ASCII forbidden-claim patterns cannot be
# evaded by homoglyphs, ZWSP or NUL. Run as a script, scripts/ci is on sys.path.
try:
    from _text_normalize import normalize_for_matching
except ImportError:  # pragma: no cover - import path fallback
    import importlib.util as _ilu

    _sp = _ilu.spec_from_file_location(
        "_text_normalize", Path(__file__).resolve().parent / "_text_normalize.py"
    )
    _tn = _ilu.module_from_spec(_sp)
    _sp.loader.exec_module(_tn)
    normalize_for_matching = _tn.normalize_for_matching

ROOT = Path(__file__).resolve().parents[2]
STATE_FILE = ROOT / "governance/project_state.yaml"

EXIT_OK = 0
EXIT_FLAGGED = 1
EXIT_ERROR = 2


class OntologyError(Exception):
    """Raised when the state file is structurally invalid (fail-closed)."""


def load_state(path: Path = STATE_FILE) -> dict[str, Any]:
    """Parse and structurally validate the SSOT. Fail-closed on any gap."""
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:  # pragma: no cover - IO edge
        raise OntologyError(f"cannot read/parse {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise OntologyError(f"{path}: top level must be a mapping")

    states = raw.get("maturity_states")
    if not isinstance(states, list) or not states:
        raise OntologyError("maturity_states must be a non-empty list")
    ranks: list[int] = []
    names: list[str] = []
    for s in states:
        if not isinstance(s, dict) or "name" not in s or "rank" not in s:
            raise OntologyError(f"maturity_states entry missing name/rank: {s!r}")
        if not str(s.get("definition", "")).strip():
            raise OntologyError(f"maturity state {s.get('name')!r} has no definition")
        names.append(s["name"])
        ranks.append(int(s["rank"]))
    if sorted(ranks) != list(range(len(states))):
        raise OntologyError(f"maturity ranks must be contiguous 0..{len(states) - 1}, got {ranks}")

    current = raw.get("current_state")
    if current not in names:
        raise OntologyError(f"current_state {current!r} is not a defined maturity state")

    classes = raw.get("evidence_classes")
    if not isinstance(classes, list) or not classes:
        raise OntologyError("evidence_classes must be a non-empty list")
    class_names: list[str] = []
    for c in classes:
        if not isinstance(c, dict) or "name" not in c:
            raise OntologyError(f"evidence_classes entry missing name: {c!r}")
        if not str(c.get("definition", "")).strip():
            raise OntologyError(f"evidence class {c.get('name')!r} has no definition")
        class_names.append(c["name"])
    class_set = set(class_names)

    firewall = raw.get("forbidden_claims")
    if not isinstance(firewall, list) or not firewall:
        raise OntologyError("forbidden_claims must be a non-empty list")
    for entry in firewall:
        if not isinstance(entry, dict) or "claim" not in entry or "pattern" not in entry:
            raise OntologyError(f"forbidden_claims entry missing claim/pattern: {entry!r}")
        requires = entry.get("requires")
        if not isinstance(requires, list) or not requires:
            raise OntologyError(f"forbidden claim {entry.get('claim')!r} has empty requires")
        unknown = [r for r in requires if r not in class_set]
        if unknown:
            raise OntologyError(
                f"forbidden claim {entry['claim']!r} requires undefined evidence class(es) {unknown}"
            )
        try:
            re.compile(entry["pattern"], re.IGNORECASE)
        except re.error as exc:
            raise OntologyError(f"forbidden claim {entry['claim']!r} bad regex: {exc}") from exc

    return raw


def validate_report(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "PASS",
        "ontology_id": state.get("ontology_id"),
        "current_state": state["current_state"],
        "maturity_states": [s["name"] for s in state["maturity_states"]],
        "evidence_classes": [c["name"] for c in state["evidence_classes"]],
        "forbidden_claims": [e["claim"] for e in state["forbidden_claims"]],
    }


def check_text(
    state: dict[str, Any],
    text: str,
    declared_class: str | None,
) -> dict[str, Any]:
    """Return a report of forbidden-claim contradictions in ``text``.

    A contradiction is a forbidden claim word present in ``text`` whose
    ``declared_class`` is not among that word's ``requires`` set (``None``
    declared class never satisfies anything -> always a contradiction).
    """
    class_names = {c["name"] for c in state["evidence_classes"]}
    if declared_class is not None and declared_class not in class_names:
        raise OntologyError(
            f"declared evidence class {declared_class!r} not in ontology vocabulary "
            f"{sorted(class_names)}"
        )

    # DS-02: fold homoglyphs / strip zero-width+control chars BEFORE matching, so
    # "vаlidаted" (Cyrillic), "valid​ated" (ZWSP) or "valid\x00ated" (NUL)
    # cannot slip a forbidden claim past the ASCII patterns.
    haystack = normalize_for_matching(text)
    contradictions: list[dict[str, Any]] = []
    for entry in state["forbidden_claims"]:
        pattern = re.compile(entry["pattern"], re.IGNORECASE)
        if not pattern.search(haystack):
            continue
        requires = list(entry["requires"])
        satisfied = declared_class is not None and declared_class in requires
        if not satisfied:
            contradictions.append(
                {
                    "claim": entry["claim"],
                    "declared_class": declared_class,
                    "requires": requires,
                    "reason": (
                        "no evidence class declared"
                        if declared_class is None
                        else f"declared class {declared_class!r} not in {requires}"
                    ),
                }
            )

    return {
        "status": "FLAGGED" if contradictions else "PASS",
        "declared_class": declared_class,
        "contradictions": sorted(contradictions, key=lambda c: c["claim"]),
        "contradiction_count": len(contradictions),
    }


def _emit(report: dict[str, Any]) -> None:
    print(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Project-state ontology claim-boundary gate.")
    parser.add_argument("--validate", action="store_true", help="Validate SSOT structure only.")
    parser.add_argument("--check-text", type=str, default=None, help="Scan literal text.")
    parser.add_argument("--check-file", type=str, default=None, help="Scan a file's text.")
    parser.add_argument(
        "--evidence-class",
        type=str,
        default=None,
        help="Declared backing evidence class for the text under check.",
    )
    parser.add_argument("--state-file", type=str, default=None, help="Override SSOT path.")
    args = parser.parse_args(argv)

    state_path = Path(args.state_file) if args.state_file else STATE_FILE
    try:
        state = load_state(state_path)
    except OntologyError as exc:
        _emit({"status": "ERROR", "error": str(exc)})
        return EXIT_ERROR

    if args.check_text is None and args.check_file is None:
        # Default / --validate mode.
        _emit(validate_report(state))
        return EXIT_OK

    if args.check_file is not None:
        try:
            text = Path(args.check_file).read_text(encoding="utf-8")
        except OSError as exc:
            _emit({"status": "ERROR", "error": f"cannot read {args.check_file}: {exc}"})
            return EXIT_ERROR
    else:
        text = args.check_text or ""

    try:
        report = check_text(state, text, args.evidence_class)
    except OntologyError as exc:
        _emit({"status": "ERROR", "error": str(exc)})
        return EXIT_ERROR

    if args.check_file is not None:
        report["source"] = args.check_file
    _emit(report)
    return EXIT_FLAGGED if report["contradiction_count"] else EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
