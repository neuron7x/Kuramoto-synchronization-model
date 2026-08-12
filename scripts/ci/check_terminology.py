#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Terminology claim gate over the operational-definition ontology (RES-003).

Reads the single source of truth ``governance/operational_definitions.json`` and
enforces, fail-closed, that a metaphor cannot be mistaken for a mechanism.

Two responsibilities:

1. ``--validate`` (default) — the ontology is internally sound. Every term is
   validated against ``schemas/operational_definition.schema.json`` AND against
   these semantic rules:

     * status must be one of {mechanism, analogue, retired} (unknown -> RED);
     * a ``mechanism`` term must carry a non-empty ``math_object``,
       ``observable_mapping`` and ``falsifier`` and at least one
       ``alternatives`` entry, with ``is_claim == true``;
     * an ``analogue`` / ``retired`` term is a non-claim (``is_claim == false``)
       and must carry a non-empty honesty ``note``;
     * a term listed in ``metaphor_only`` (or any analogue/retired name) MUST NOT
       be labelled ``mechanism`` (a metaphor labelled mechanism -> RED);
     * term names are unique.

2. ``--assert TERM --as STATUS`` — the CLAIM gate. A doc/PR asserts that it uses
   ``TERM`` as ``STATUS`` (typically ``mechanism``). The gate flags the claim when
   the ontology does not support it: the term is unknown, is defined with a
   different status, or is a mechanism term that is missing its operational
   mapping / falsifier / alternatives. This is how a claim that uses a term as a
   mechanism without an operational definition gets flagged.

Exit codes (mirrors the project-state ontology gate):
  0  clean / claim supported
  1  a contradiction was found (ontology unsound, or claim unsupported)
  2  the ontology file or schema could not be read/parsed (hard error)

Every mode prints a deterministic JSON report to stdout.

Usage::

    python scripts/ci/check_terminology.py --validate
    python scripts/ci/check_terminology.py --assert synchronization --as mechanism
    python scripts/ci/check_terminology.py --assert serotonin --as mechanism   # flagged
    python scripts/ci/check_terminology.py --validate --file /path/to/other.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

try:
    import jsonschema
except ModuleNotFoundError as exc:  # DS-18: fail cleanly, never raw traceback
    print(json.dumps({"status": "ERROR", "error": f"missing dependency: {exc.name}"}))
    sys.exit(2)

# Confusable/zero-width normalization so a term name carrying a homoglyph, ZWSP or
# NUL still resolves to its ontology entry instead of reading as "undefined".
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
ONTOLOGY_FILE = ROOT / "governance/operational_definitions.json"
SCHEMA_FILE = ROOT / "schemas/operational_definition.schema.json"

VALID_STATUSES = ("mechanism", "analogue", "retired")

EXIT_OK = 0
EXIT_FLAGGED = 1
EXIT_ERROR = 2


class OntologyError(Exception):
    """Raised when the ontology or schema cannot be read/parsed (fail-closed)."""


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise OntologyError(f"cannot read/parse {path}: {exc}") from exc


def load_ontology(path: Path = ONTOLOGY_FILE) -> dict[str, Any]:
    data = _load_json(path)
    if not isinstance(data, dict):
        raise OntologyError(f"{path}: top level must be a mapping")
    return data


def _is_nonempty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def schema_issues(ontology: dict[str, Any], schema_path: Path = SCHEMA_FILE) -> list[str]:
    """Return every JSON-schema validation error as a stable, sorted list."""
    schema = _load_json(schema_path)
    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(ontology), key=lambda e: list(e.absolute_path))
    out: list[str] = []
    for err in errors:
        loc = "/".join(str(p) for p in err.absolute_path) or "<root>"
        out.append(f"schema[{loc}]: {err.message}")
    return out


def semantic_issues(ontology: dict[str, Any]) -> list[str]:
    """Return every semantic (mechanism-vs-metaphor) contradiction, fail-closed."""
    issues: list[str] = []
    terms = ontology.get("terms")
    if not isinstance(terms, list) or not terms:
        return ["ontology has no terms list"]

    metaphor_only = {str(n) for n in ontology.get("metaphor_only", []) if isinstance(n, str)}
    seen: set[str] = set()

    for idx, term in enumerate(terms):
        if not isinstance(term, dict):
            issues.append(f"term[{idx}] is not a mapping")
            continue
        name = term.get("name")
        label = name if _is_nonempty_str(name) else f"term[{idx}]"
        if _is_nonempty_str(name):
            if name in seen:
                issues.append(f"{name}: duplicate term name")
            seen.add(str(name))
        else:
            issues.append(f"{label}: missing/empty name")

        status = term.get("status")
        if status not in VALID_STATUSES:
            issues.append(
                f"{label}: unknown status {status!r} (must be one of {list(VALID_STATUSES)})"
            )
            # An unknown status cannot be reasoned about further; keep going.
            continue

        is_claim = term.get("is_claim")

        if status == "mechanism":
            if is_claim is not True:
                issues.append(f"{label}: mechanism term must set is_claim: true")
            if not _is_nonempty_str(term.get("math_object")):
                issues.append(f"{label}: mechanism term missing math_object")
            if not _is_nonempty_str(term.get("observable_mapping")):
                issues.append(f"{label}: mechanism term missing observable_mapping")
            if not _is_nonempty_str(term.get("falsifier")):
                issues.append(f"{label}: mechanism term missing falsifier")
            alts = term.get("alternatives")
            if not isinstance(alts, list) or not any(_is_nonempty_str(a) for a in alts):
                issues.append(f"{label}: mechanism term missing alternative hypotheses")
            if _is_nonempty_str(name) and name in metaphor_only:
                issues.append(
                    f"{label}: metaphor-only term labelled mechanism "
                    f"(must be analogue or retired, never mechanism)"
                )
        else:  # analogue or retired
            if is_claim is not False:
                issues.append(f"{label}: {status} term is a non-claim and must set is_claim: false")
            if not _is_nonempty_str(term.get("note")):
                issues.append(f"{label}: {status} term must carry an honesty note")

    return sorted(issues)


def validate_report(ontology: dict[str, Any], schema_path: Path = SCHEMA_FILE) -> dict[str, Any]:
    issues = sorted(schema_issues(ontology, schema_path) + semantic_issues(ontology))
    terms = [t for t in ontology.get("terms", []) if isinstance(t, dict)]
    counts = {s: sum(1 for t in terms if t.get("status") == s) for s in VALID_STATUSES}
    return {
        "status": "FLAGGED" if issues else "PASS",
        "ontology_id": ontology.get("ontology_id"),
        "term_count": len(terms),
        "counts": counts,
        "terms": [t.get("name") for t in terms],
        "issues": issues,
        "issue_count": len(issues),
    }


def _find_term(ontology: dict[str, Any], name: str) -> dict[str, Any] | None:
    # DS-02: match on the confusable/zero-width-folded form so an assertion that
    # spells a term with a Cyrillic look-alike / ZWSP / NUL still resolves to its
    # real ontology entry (and is judged on that entry's status) rather than
    # reading as "no operational definition".
    target = normalize_for_matching(name)
    for term in ontology.get("terms", []):
        if not isinstance(term, dict):
            continue
        candidates = [term.get("name"), *(term.get("aliases") or [])]
        for cand in candidates:
            if isinstance(cand, str) and normalize_for_matching(cand) == target:
                return term
    return None


def assert_report(ontology: dict[str, Any], name: str, claimed_status: str) -> dict[str, Any]:
    """Flag a claim that uses ``name`` as ``claimed_status`` when unsupported."""
    contradictions: list[str] = []
    term = _find_term(ontology, name)
    resolved = term.get("name") if term else None
    defined_status = term.get("status") if term else None

    if term is None:
        contradictions.append(f"term {name!r} has no operational definition in the ontology")
    elif defined_status != claimed_status:
        contradictions.append(
            f"term {name!r} is defined as {defined_status!r}, not {claimed_status!r}"
        )
    elif claimed_status == "mechanism":
        # Supported status match, but re-check the mechanism carries a mapping.
        if not _is_nonempty_str(term.get("observable_mapping")):
            contradictions.append(f"term {name!r} mechanism lacks an observable_mapping")
        if not _is_nonempty_str(term.get("falsifier")):
            contradictions.append(f"term {name!r} mechanism lacks a falsifier")
        alts = term.get("alternatives")
        if not isinstance(alts, list) or not any(_is_nonempty_str(a) for a in alts):
            contradictions.append(f"term {name!r} mechanism lacks alternative hypotheses")

    return {
        "status": "FLAGGED" if contradictions else "PASS",
        "term": name,
        "resolved_name": resolved,
        "claimed_status": claimed_status,
        "defined_status": defined_status,
        "contradictions": contradictions,
        "contradiction_count": len(contradictions),
    }


def _emit(report: dict[str, Any]) -> None:
    print(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Operational-definition terminology gate.")
    parser.add_argument("--validate", action="store_true", help="Validate the ontology (default).")
    parser.add_argument(
        "--assert",
        dest="assert_term",
        type=str,
        default=None,
        help="Claim gate: assert TERM is used as --as STATUS.",
    )
    parser.add_argument(
        "--as",
        dest="claimed_status",
        type=str,
        default="mechanism",
        help="Status claimed for --assert TERM (default: mechanism).",
    )
    parser.add_argument("--file", type=str, default=None, help="Override the ontology path.")
    parser.add_argument("--schema", type=str, default=None, help="Override the schema path.")
    args = parser.parse_args(argv)

    ontology_path = Path(args.file) if args.file else ONTOLOGY_FILE
    try:
        ontology = load_ontology(ontology_path)
        if args.schema:
            # Fail-closed if a custom schema cannot be read.
            _load_json(Path(args.schema))
    except OntologyError as exc:
        _emit({"status": "ERROR", "error": str(exc)})
        return EXIT_ERROR

    if args.assert_term is not None:
        report = assert_report(ontology, args.assert_term, args.claimed_status)
        report["source"] = str(ontology_path)
        _emit(report)
        return EXIT_FLAGGED if report["contradiction_count"] else EXIT_OK

    # Default / --validate mode.
    schema_path = Path(args.schema) if args.schema else SCHEMA_FILE
    try:
        report = validate_report(ontology, schema_path)
    except OntologyError as exc:
        _emit({"status": "ERROR", "error": str(exc)})
        return EXIT_ERROR
    report["source"] = str(ontology_path)
    _emit(report)
    return EXIT_FLAGGED if report["issue_count"] else EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
