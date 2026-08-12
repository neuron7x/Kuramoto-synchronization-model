#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Validate company-grade value functions.

The manifest converts company values into measurable engineering constraints:
value -> invariant -> evidence surface -> fail-closed verdict.

Stdlib-only by design so governance can run without trusting the dependency graph.
"""

from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "data" / "governance" / "company_value_functions.json"
REQUIRED_IDS = tuple(f"VF-{idx:02d}" for idx in range(1, 8))
REQUIRED_DECISION_FLAGS = (
    "hard_constraints_first",
    "forbid_green_by_vacuum",
    "forbid_unmeasured_success_claims",
    "fail_closed_on_missing_evidence",
)
EXECUTABLE_PREFIXES = ("tools/", "scripts/", ".github/")
CI_PREFIX = ".github/workflows/"


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _is_non_empty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_non_empty_list(value: Any) -> bool:
    return isinstance(value, list) and bool(value)


def _surface_path(repo_root: Path, surface: str) -> Path:
    return repo_root / surface.rstrip("/")


def _surface_exists(repo_root: Path, surface: str) -> bool:
    return _surface_path(repo_root, surface).exists()


def _has_surface_prefix(vf: dict[str, Any], prefixes: tuple[str, ...]) -> bool:
    surfaces = vf.get("evidence_surfaces", [])
    return any(str(surface).startswith(prefixes) for surface in surfaces)


def check(path: Path = MANIFEST, repo_root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    try:
        data = _load(path)
    except (OSError, json.JSONDecodeError) as exc:
        return [f"{path}: cannot load value-function manifest: {exc}"]

    if data.get("schema") != "geosync.company_value_functions.v1":
        errors.append(f"{path}: schema must be geosync.company_value_functions.v1")
    if data.get("status") != "normative":
        errors.append(f"{path}: status must be normative")

    decision_rule = data.get("decision_rule")
    if not isinstance(decision_rule, dict):
        errors.append(f"{path}: decision_rule must be an object")
        decision_rule = {}
    for flag in REQUIRED_DECISION_FLAGS:
        if decision_rule.get(flag) is not True:
            errors.append(f"{path}: decision_rule.{flag} must be true")
    minimum_total = decision_rule.get("minimum_total_score")
    if not isinstance(minimum_total, float | int) or minimum_total < 0.92:
        errors.append(f"{path}: minimum_total_score must be >= 0.92")
    minimum_individual = decision_rule.get("minimum_individual_score")
    if not isinstance(minimum_individual, float | int) or minimum_individual < 0.80:
        errors.append(f"{path}: minimum_individual_score must be >= 0.80")

    value_functions = data.get("value_functions")
    if not isinstance(value_functions, list):
        return errors + [f"{path}: value_functions must be a list"]
    if len(value_functions) != len(REQUIRED_IDS):
        errors.append(f"{path}: expected {len(REQUIRED_IDS)} value functions")

    ids: list[str] = []
    total_weight = 0.0
    hard_constraints = 0
    for idx, vf in enumerate(value_functions, start=1):
        prefix = f"{path}: value_functions[{idx}]"
        if not isinstance(vf, dict):
            errors.append(f"{prefix}: must be an object")
            continue
        vf_id = vf.get("id")
        ids.append(str(vf_id))
        if vf_id not in REQUIRED_IDS:
            errors.append(f"{prefix}: invalid id {vf_id!r}")
        for key in ("name", "principle"):
            if not _is_non_empty_str(vf.get(key)):
                errors.append(f"{prefix}: {key} must be a non-empty string")
        weight = vf.get("weight")
        if not isinstance(weight, float | int) or weight <= 0:
            errors.append(f"{prefix}: weight must be positive")
        else:
            total_weight += float(weight)
        is_hard_constraint = vf.get("hard_constraint") is True
        if is_hard_constraint:
            hard_constraints += 1
        elif vf.get("hard_constraint") is not False:
            errors.append(f"{prefix}: hard_constraint must be boolean")
        for key in (
            "measurable_invariants",
            "evidence_surfaces",
            "score_inputs",
            "failure_modes",
        ):
            values = vf.get(key)
            if not _is_non_empty_list(values):
                errors.append(f"{prefix}: {key} must be a non-empty list")
                continue
            if len(values) < 3:
                errors.append(f"{prefix}: {key} must contain at least three entries")
            if not all(_is_non_empty_str(item) for item in values):
                errors.append(f"{prefix}: {key} must contain only non-empty strings")
        surfaces = vf.get("evidence_surfaces")
        if not isinstance(surfaces, list):
            continue
        for surface in surfaces:
            if not isinstance(surface, str) or not surface.strip():
                continue
            if not _surface_exists(repo_root, surface):
                errors.append(f"{prefix}: evidence surface does not exist: {surface}")
        if not _has_surface_prefix(vf, EXECUTABLE_PREFIXES):
            errors.append(f"{prefix}: at least one evidence surface must be executable/CI")
        if is_hard_constraint and not _has_surface_prefix(vf, (CI_PREFIX,)):
            errors.append(f"{prefix}: hard constraints must include a CI workflow surface")

    if tuple(ids) != REQUIRED_IDS:
        errors.append(f"{path}: value function ids must be ordered {REQUIRED_IDS}")
    if abs(total_weight - 1.0) > 0.000001:
        errors.append(f"{path}: value function weights must sum to 1.0, got {total_weight:.6f}")
    if hard_constraints < 3:
        errors.append(f"{path}: at least three value functions must be hard constraints")

    return errors


def _check_mutation(
    payload: dict[str, Any], repo_root: Path, expected_fragment: str, name: str
) -> list[str]:
    with TemporaryDirectory() as temp_dir:
        manifest = Path(temp_dir) / "company_value_functions.json"
        _write(manifest, payload)
        observed = check(manifest, repo_root)
    if any(expected_fragment in error for error in observed):
        return []
    return [
        f"self-test {name!r} did not trigger expected error fragment "
        f"{expected_fragment!r}; observed={observed!r}"
    ]


def self_test(path: Path = MANIFEST, repo_root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    try:
        base = _load(path)
    except (OSError, json.JSONDecodeError) as exc:
        return [f"{path}: cannot load value-function manifest for self-test: {exc}"]

    control_errors = check(path, repo_root)
    if control_errors:
        errors.append(f"self-test positive control failed: {control_errors!r}")
        return errors

    payload = deepcopy(base)
    payload["value_functions"][0]["weight"] = 0.50
    errors.extend(_check_mutation(payload, repo_root, "weights must sum to 1.0", "weight drift"))

    payload = deepcopy(base)
    payload["decision_rule"]["fail_closed_on_missing_evidence"] = False
    errors.extend(
        _check_mutation(
            payload,
            repo_root,
            "fail_closed_on_missing_evidence",
            "fail-closed softening",
        )
    )

    payload = deepcopy(base)
    payload["value_functions"][0]["evidence_surfaces"].append("tools/missing_value_gate.py")
    errors.extend(
        _check_mutation(
            payload,
            repo_root,
            "evidence surface does not exist",
            "missing evidence surface",
        )
    )

    payload = deepcopy(base)
    payload["value_functions"][0]["evidence_surfaces"] = [
        "constraints/security.txt",
        "requirements-scan.txt",
        "tools/deps/check_operational_dependency_determinism.py",
    ]
    errors.extend(
        _check_mutation(
            payload,
            repo_root,
            "hard constraints must include a CI workflow surface",
            "hard constraint without CI surface",
        )
    )

    payload = deepcopy(base)
    payload["value_functions"][1]["failure_modes"] = []
    errors.extend(
        _check_mutation(
            payload,
            repo_root,
            "failure_modes must be a non-empty list",
            "missing failure modes",
        )
    )

    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)

    errors = check(args.manifest, args.repo_root)
    if not errors and args.self_test:
        errors = self_test(args.manifest, args.repo_root)
    if errors:
        print("COMPANY VALUE FUNCTION GATE: FAIL", file=sys.stderr)
        for error in errors:
            print(f"  {error}", file=sys.stderr)
        return 1
    print("COMPANY VALUE FUNCTION GATE: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
