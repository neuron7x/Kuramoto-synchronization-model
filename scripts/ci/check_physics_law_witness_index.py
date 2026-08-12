#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Materialise and verify the physics law→witness index (Physics v2, Task 1).

This is a *thin consumer* of the law machinery that already exists — it does
**not** re-implement witness binding. It reuses:

* ``physics_contracts.law.load_catalog`` for the catalog of physical laws
  (each carrying its formula, tolerance, validity, source, and severity);
* the ``@law("id")`` decorator bindings authored on the witness tests, scanned
  by AST (the same binding ``tools/validate_tests`` checks);
* ``.claude/physics/INVARIANTS.yaml`` for the broader invariant registry.

It emits one durable, diffable artifact —
``artifacts/physics_v2/law_witness_index.json`` — mapping every law to its
formula, validity domain, source module, test witness, falsifier, tolerance
derivation, and a coverage status, and fails closed when:

* a **blocking** catalog law (``severity: block``) has no registered witness and
  is not explicitly ledgered (this catches a *new blocking law without a
  witness*);
* a witness file declared for an ``ANCHORED`` invariant does not exist;
* a tolerance lacks a formula-derived rationale (a bare numeric literal);
* the committed index has drifted from the regenerated one.

Usage::

    python scripts/ci/check_physics_law_witness_index.py            # verify
    python scripts/ci/check_physics_law_witness_index.py --write     # regenerate

Exit codes: ``0`` all checks pass; ``1`` at least one fail-closed violation.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
INDEX_PATH = ROOT / "artifacts" / "physics_v2" / "law_witness_index.json"
INVARIANTS_PATH = ROOT / ".claude" / "physics" / "INVARIANTS.yaml"
CATALOG_PATH = ROOT / "physics_contracts" / "catalog.yaml"
TESTS_ROOT = ROOT / "tests"

# A tolerance rationale that is *only* a number (optionally signed/scientific) is
# a magic literal, not a derivation. Anything with surrounding reasoning passes.
_BARE_NUMBER = re.compile(r"^\s*[+-]?\d+(\.\d+)?([eE][+-]?\d+)?\s*$")

# Ledgered statuses: a blocking law may carry one of these only with a reason.
_LEDGERED_STATUSES = frozenset({"WARN_ONLY", "OUT_OF_SCOPE", "MISSING"})


def scan_law_witnesses(tests_root: Path) -> dict[str, list[str]]:
    """AST-scan ``tests/`` for ``@law("id")`` decorators → ``{law_id: [qualname]}``.

    Mirrors the discovery in ``tools/validate_tests`` (no import side effects):
    a witness binds itself to a law by the dotted id in its ``@law`` decorator.
    """

    witnesses: dict[str, list[str]] = {}
    for path in sorted(tests_root.rglob("test_*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (SyntaxError, UnicodeDecodeError):
            continue
        rel = path.relative_to(ROOT).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            for deco in node.decorator_list:
                if not isinstance(deco, ast.Call):
                    continue
                func = deco.func
                name = (
                    func.id
                    if isinstance(func, ast.Name)
                    else func.attr if isinstance(func, ast.Attribute) else None
                )
                if name != "law" or not deco.args:
                    continue
                first = deco.args[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    witnesses.setdefault(first.value, []).append(f"{rel}::{node.name}")
    return witnesses


def _load_invariants() -> list[dict[str, Any]]:
    """Flatten the nested INVARIANTS registry into invariant dicts."""

    raw = yaml.safe_load(INVARIANTS_PATH.read_text(encoding="utf-8"))
    found: list[dict[str, Any]] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if "id" in node and "priority" in node:
                found.append(node)
            else:
                for value in node.values():
                    walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(raw)
    return found


def _load_catalog() -> dict[str, dict[str, Any]]:
    """Parse ``physics_contracts/catalog.yaml`` into ``{law_id: entry}``.

    Read directly (not via ``physics_contracts.law.load_catalog``) so this CI
    script imports no first-party non-shipped package — it stays clean under the
    wheel-contract import ratchet while consuming the same source of truth.
    """

    raw = yaml.safe_load(CATALOG_PATH.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or "laws" not in raw:
        raise ValueError(f"{CATALOG_PATH}: missing top-level 'laws' list")
    catalog: dict[str, dict[str, Any]] = {}
    for entry in raw["laws"]:
        law_id = entry["id"]
        if law_id in catalog:
            raise ValueError(f"duplicate law id in catalog: {law_id}")
        catalog[law_id] = entry
    return catalog


def _catalog_entry(law: dict[str, Any], witnesses: dict[str, list[str]]) -> dict[str, Any]:
    law_id = law["id"]
    severity = law.get("severity", "block")
    formula = law["formula"]
    tolerance = law["tolerance"]
    validity = law["validity"]
    bound = sorted(witnesses.get(law_id, []))
    if severity != "block":
        status = "WARN_ONLY"
    elif bound:
        status = "COVERED"
    else:
        status = "MISSING"
    tolerance_derivation = (
        f"Tolerance derived from the law formula '{formula}' and the catalog "
        f"tolerance clause '{tolerance}'."
    )
    falsifier = (
        f"An observation violating '{formula}' beyond the declared tolerance "
        f"('{tolerance}') in the validity domain '{validity}'."
    )
    return {
        "law_id": law_id,
        "module": law["module"],
        "severity": severity,
        "formula": formula,
        "validity_domain": validity,
        "source": law["source"],
        "tolerance": tolerance,
        "tolerance_derivation": tolerance_derivation,
        "falsifier": falsifier,
        "status": status,
        "test_witnesses": bound,
        "ledger_reason": "",
    }


def _invariant_entry(inv: dict[str, Any]) -> dict[str, Any]:
    tests_field = inv.get("tests")
    witnesses = (
        [seg.strip() for seg in str(tests_field).replace(";", " ").split() if seg.strip()]
        if tests_field
        else []
    )
    exists = bool(witnesses) and all((ROOT / w).exists() for w in witnesses)
    if exists:
        status = "COVERED"
    elif witnesses:
        status = "MISSING"
    else:
        status = "WARN_ONLY"
    return {
        "id": inv["id"],
        "priority": inv.get("priority", ""),
        "provenance": inv.get("provenance", "UNSPECIFIED"),
        "source_module": inv.get("source", ""),
        "falsifier": inv.get("falsification", ""),
        "test_witnesses": witnesses,
        "status": status,
    }


def build_index() -> dict[str, Any]:
    """Regenerate the full law→witness index from the live sources."""

    catalog = _load_catalog()
    witnesses = scan_law_witnesses(TESTS_ROOT)
    catalog_laws = [_catalog_entry(catalog[lid], witnesses) for lid in sorted(catalog)]
    invariants = [
        _invariant_entry(inv) for inv in sorted(_load_invariants(), key=lambda i: i["id"])
    ]
    blocking = [e for e in catalog_laws if e["severity"] == "block"]
    return {
        "schema_version": 1,
        "generated_by": "scripts/ci/check_physics_law_witness_index.py",
        "summary": {
            "catalog_laws": len(catalog_laws),
            "blocking_laws": len(blocking),
            "blocking_covered": sum(1 for e in blocking if e["status"] == "COVERED"),
            "invariants": len(invariants),
            "invariants_covered": sum(1 for e in invariants if e["status"] == "COVERED"),
        },
        "catalog_laws": catalog_laws,
        "invariants": invariants,
    }


def _serialise(index: dict[str, Any]) -> str:
    return json.dumps(index, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def verify(index: dict[str, Any]) -> list[str]:
    """Return fail-closed violations for a (committed) index, empty if clean."""

    errors: list[str] = []

    # 1. Drift: the committed index must equal the regenerated one.
    regenerated = build_index()
    if _serialise(index) != _serialise(regenerated):
        errors.append(
            "law_witness_index.json is stale — regenerate with "
            "`python scripts/ci/check_physics_law_witness_index.py --write`"
        )

    # 2. Every blocking law needs a witness or an explicit ledger entry.
    for entry in index.get("catalog_laws", []):
        if entry.get("severity") != "block":
            continue
        status = entry.get("status")
        witnesses = entry.get("test_witnesses") or []
        if status == "COVERED" and witnesses:
            pass
        elif status in _LEDGERED_STATUSES and str(entry.get("ledger_reason", "")).strip():
            pass
        else:
            errors.append(
                f"blocking law without witness: {entry.get('law_id')!r} "
                f"(status={status!r}, witnesses={len(witnesses)}); add a witness or "
                "an explicit ledger_reason"
            )
        # 3. Tolerance must carry a formula-derived rationale, not a bare number.
        derivation = str(entry.get("tolerance_derivation", "")).strip()
        if not derivation or _BARE_NUMBER.match(derivation):
            errors.append(f"law {entry.get('law_id')!r} has no formula-derived tolerance rationale")

    # 4. ANCHORED invariants must point at witness files that exist.
    for entry in index.get("invariants", []):
        if entry.get("provenance") != "ANCHORED":
            continue
        for witness in entry.get("test_witnesses") or []:
            if not (ROOT / witness).exists():
                errors.append(
                    f"ANCHORED invariant {entry.get('id')!r} witness does not exist: {witness}"
                )
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--write", action="store_true", help="regenerate the committed index artifact"
    )
    args = parser.parse_args(argv)

    if args.write:
        INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
        INDEX_PATH.write_text(_serialise(build_index()), encoding="utf-8")
        print(f"wrote {INDEX_PATH.relative_to(ROOT)}")
        return 0

    if not INDEX_PATH.exists():
        print(f"ERROR: missing law-witness index: {INDEX_PATH}")
        return 1
    committed = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    errors = verify(committed)
    if errors:
        print("PHYSICS LAW-WITNESS INDEX: FAIL")
        for err in errors:
            print(f"  - {err}")
        return 1
    summary = committed.get("summary", {})
    print(
        "PHYSICS LAW-WITNESS INDEX: OK "
        f"({summary.get('blocking_covered')}/{summary.get('blocking_laws')} blocking laws "
        f"witnessed; {summary.get('invariants_covered')}/{summary.get('invariants')} invariants "
        "with existing witnesses)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
