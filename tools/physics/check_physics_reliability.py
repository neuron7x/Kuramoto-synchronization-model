# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Fail-closed checker for the physics module reliability contract.

Well-Architected reliability discipline for physics gates: a green test is not a
reliability claim. This checker enforces that every *declared* physics module
publishes a grounded failure_mode / blast_radius / degradation_mode /
recovery_command, that each bound invariant is literally present in the module
source, and that the covered count never drops below the ratchet floor.

It does NOT silently pass on incompleteness: every INV-bearing module under the
scope roots that lacks a contract entry is reported BY NAME as the explicit
backlog. The contract names its own uncovered area rather than implying full
coverage.

Usage::

    python tools/physics/check_physics_reliability.py            # human report
    python tools/physics/check_physics_reliability.py --json     # machine report
    python tools/physics/check_physics_reliability.py --strict-coverage  # also fail on any uncovered module

Exit code 0 iff no HARD violations (schema/source/ratchet); non-zero otherwise.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = REPO_ROOT / "governance" / "PHYSICS_RELIABILITY.yaml"
SCHEMA_PATH = REPO_ROOT / "schemas" / "physics" / "reliability_contract.schema.json"

_INV_TOKEN = re.compile(r"\bINV-[A-Z0-9]+\b")
# A recovery_command must be executable-shaped: a runnable command or a named
# fail-closed action, not free prose. At least one of these action tokens.
_RECOVERY_ACTION = re.compile(
    r"\b(raise|return|rerun|re-solve|regenerate|fail-closed|python|pytest|git)\b"
)


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        data: Any = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a mapping at the top level")
    return data


def _modules_with_invariants(root: Path) -> dict[str, set[str]]:
    """Map every *.py under ``root`` that references an INV-* tag to its tags."""
    found: dict[str, set[str]] = {}
    if not root.exists():
        return found
    for py in sorted(root.rglob("*.py")):
        try:
            text = py.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        tags = set(_INV_TOKEN.findall(text))
        if tags:
            found[str(py.relative_to(REPO_ROOT))] = tags
    return found


def _schema_validate(contract: dict[str, Any]) -> list[str]:
    """Validate against the JSON schema if jsonschema is importable; else a
    minimal structural fallback so the gate never silently no-ops."""
    try:
        import jsonschema
    except ImportError:
        required = {"version", "coverage_floor", "scope_roots", "modules"}
        missing = sorted(required - set(contract))
        return [f"contract missing top-level key: {k}" for k in missing]
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = jsonschema.Draft7Validator(schema)
    return [
        f"schema: {'/'.join(str(p) for p in err.path)}: {err.message}"
        for err in sorted(validator.iter_errors(contract), key=lambda e: list(e.path))
    ]


def check(
    *, strict_coverage: bool = False, contract: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Run the contract check and return a structured result.

    ``contract`` defaults to the on-disk PHYSICS_RELIABILITY.yaml; passing a dict
    lets callers (and mutation tests) exercise the detection logic on synthetic
    contracts — e.g. an entry citing a phantom invariant the module lacks.
    """
    hard: list[str] = []
    if contract is None:
        contract = _load_yaml(CONTRACT_PATH)
    hard.extend(_schema_validate(contract))

    scope_roots = contract.get("scope_roots", []) if not hard else []
    in_scope: dict[str, set[str]] = {}
    for rel in scope_roots:
        in_scope.update(_modules_with_invariants(REPO_ROOT / str(rel)))

    entries = contract.get("modules", []) if isinstance(contract.get("modules"), list) else []
    covered: list[str] = []
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            hard.append(f"module entry is not a mapping: {entry!r}")
            continue
        mod = str(entry.get("module", ""))
        covered.append(mod)
        if mod in seen:
            hard.append(f"{mod}: duplicate module entry")
        seen.add(mod)
        mod_path = REPO_ROOT / mod
        if not mod_path.is_file():
            hard.append(f"{mod}: declared module file does not exist")
            continue
        source = mod_path.read_text(encoding="utf-8")
        present = set(_INV_TOKEN.findall(source))
        for inv in entry.get("invariants", []):
            if inv not in present:
                hard.append(f"{mod}: declared invariant {inv} not found in module source")
        recovery = str(entry.get("recovery_command", ""))
        if not _RECOVERY_ACTION.search(recovery):
            hard.append(
                f"{mod}: recovery_command is not executable-shaped "
                f"(needs a runnable command or named fail-closed action): {recovery!r}"
            )

    floor = int(contract.get("coverage_floor", 0))
    if len(covered) < floor:
        hard.append(
            f"coverage ratchet: {len(covered)} covered < floor {floor} "
            f"(entries were removed without lowering the floor)"
        )

    uncovered = sorted(set(in_scope) - set(covered))
    if strict_coverage and uncovered:
        hard.append(f"strict-coverage: {len(uncovered)} INV-bearing modules lack a contract entry")

    return {
        "covered_count": len(covered),
        "in_scope_count": len(in_scope),
        "coverage_floor": floor,
        "uncovered_modules": uncovered,
        "hard_violations": hard,
        "passed": not hard,
    }


def _print_human(result: dict[str, Any]) -> None:
    print("=" * 64)
    print("Physics Module Reliability Contract")
    print("=" * 64)
    print(f"Covered modules:   {result['covered_count']}")
    print(f"In-scope (INV):    {result['in_scope_count']}")
    print(f"Coverage floor:    {result['coverage_floor']}")
    uncovered = result["uncovered_modules"]
    if uncovered:
        print(f"\nUncovered INV-bearing modules ({len(uncovered)}) — explicit backlog:")
        for mod in uncovered:
            print(f"  - {mod}")
    hard = result["hard_violations"]
    if hard:
        print(f"\nHARD violations ({len(hard)}):")
        for v in hard:
            print(f"  [X] {v}")
        print("\nFAIL")
    else:
        print("\nNo hard violations. Declared entries are grounded and ratchet holds.")
        print("PASS")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    parser.add_argument(
        "--strict-coverage",
        action="store_true",
        help="also fail if any INV-bearing module lacks a contract entry",
    )
    args = parser.parse_args(argv)
    result = check(strict_coverage=args.strict_coverage)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        _print_human(result)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
