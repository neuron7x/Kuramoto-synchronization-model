#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Claim-to-artifact graph gate (second-layer hardening).

A research claim is only as trustworthy as the proof chain behind it:

    claim → contract → schema → data/config hash → artifact → validator → test

The truth gate (``check_research_artifact_truth.py``) judges a single artifact
in isolation. This gate judges the *graph*: that each research line's declared
``state``/``claim.tier`` is actually backed by an artifact whose data hash, git
SHA, and falsification status earn that tier — and that the schema and artifact
the contract points at exist and are semantically honest.

Rules (per ``research_lines/*/contract.yaml``):

* the referenced schema and example artifact must exist;
* a ``TESTED_REAL_*`` / ``MEASURED`` / ``REPLICATED`` / ``VALIDATED`` state, or a
  ``LIMITED_EMPIRICAL`` / ``MEASURED_*`` tier, requires an artifact with a
  non-zero ``data_sha256`` (and non-zero ``git_sha`` for empirical tiers);
* a ``HYPOTHESIS`` / ``INSTRUMENTED`` line may use a placeholder, but its artifact
  may not be evidence-bearing (``falsification_status: PASS``);
* ``falsification_status: PASS`` requires a declared falsifier or null baseline;
* the artifact must pass the canonical semantic-truth rules.

Run::

    python scripts/ci/check_claim_artifact_graph.py

Exit codes::

    0  — every claim maps to a coherent, honest proof chain
    1  — at least one claim is unbacked, over-stated, or contradicted
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
ZERO_SHA256 = "0" * 64
ZERO_SHA1_GIT = "0" * 40

# States that assert a real run has happened.
EVIDENCE_STATES: frozenset[str] = frozenset(
    {"TESTED_REAL_SINGLE", "TESTED_REAL_MULTI", "MEASURED", "REPLICATED", "VALIDATED"}
)
# Tiers that assert empirical measurement.
EVIDENCE_TIERS: frozenset[str] = frozenset(
    {"LIMITED_EMPIRICAL", "MEASURED_SINGLE", "MEASURED_MULTI"}
)
# Lines that may legitimately carry a zero-hash placeholder.
NON_EVIDENCE_TIERS: frozenset[str] = frozenset({"HYPOTHESIS", "INSTRUMENTED"})


def _load_truth_gate() -> Any:
    gate_path = ROOT / "scripts" / "ci" / "check_research_artifact_truth.py"
    spec = importlib.util.spec_from_file_location("_truth_gate", gate_path)
    if spec is None or spec.loader is None:  # pragma: no cover - import plumbing
        raise RuntimeError(f"cannot load truth gate at {gate_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _get(d: Any, *keys: str, default: Any = None) -> Any:
    cur: Any = d
    for key in keys:
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


def evaluate_contract(
    contract_path: Path, data: Any, repo_root: Path, truth_gate: Any
) -> list[str]:
    """Return graph-consistency violations for one research-line contract."""
    errors: list[str] = []
    rel = (
        contract_path.relative_to(repo_root).as_posix()
        if contract_path.is_absolute()
        else contract_path.as_posix()
    )

    if not isinstance(data, dict):
        return [f"{rel}: contract is not a mapping"]

    line_id = data.get("line_id", "<unknown>")
    state = data.get("state")
    tier = _get(data, "claim", "tier")
    schema_rel = _get(data, "inference_contract", "canonical_schema")
    artifact_rel = _get(data, "artifact", "example")

    # --- schema node must exist ---
    if not schema_rel:
        errors.append(f"{rel}: {line_id}: contract declares no canonical_schema")
    elif not (repo_root / schema_rel).is_file():
        errors.append(f"{rel}: {line_id}: schema not found: {schema_rel}")

    # --- artifact node must exist ---
    if not artifact_rel:
        errors.append(f"{rel}: {line_id}: contract declares no example artifact")
        return errors
    artifact_path = repo_root / artifact_rel
    if not artifact_path.is_file():
        errors.append(f"{rel}: {line_id}: artifact not found: {artifact_rel}")
        return errors

    try:
        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return errors + [f"{rel}: {line_id}: unreadable artifact {artifact_rel} ({exc})"]
    if not isinstance(artifact, dict):
        return errors + [f"{rel}: {line_id}: artifact {artifact_rel} is not an object"]

    data_sha = artifact.get("data_sha256")
    git_sha = artifact.get("git_sha")
    status = artifact.get("falsification_status")
    zero_data = data_sha in (None, "", ZERO_SHA256)
    zero_git = git_sha in (None, "", ZERO_SHA1_GIT)

    is_evidence_claim = state in EVIDENCE_STATES or tier in EVIDENCE_TIERS

    # --- tier/state ↔ data-hash consistency (the central anti-lie rule) ---
    if is_evidence_claim and zero_data:
        errors.append(
            f"{rel}: {line_id}: state={state!r}/tier={tier!r} asserts evidence "
            f"but artifact {artifact_rel} has zero data_sha256"
        )
    if tier in EVIDENCE_TIERS and zero_git:
        errors.append(
            f"{rel}: {line_id}: empirical tier {tier!r} requires a non-zero git_sha "
            f"in {artifact_rel}"
        )

    # --- non-evidence line must not ship an evidence-bearing artifact ---
    if (tier in NON_EVIDENCE_TIERS or state in NON_EVIDENCE_TIERS) and status == "PASS":
        errors.append(
            f"{rel}: {line_id}: {tier or state} line cannot ship a PASS artifact ({artifact_rel})"
        )

    # --- PASS requires a declared falsifier or null baseline ---
    if status == "PASS":
        has_falsifier = bool(_get(data, "claim", "falsifier"))
        has_nulls = bool(_get(data, "falsification", "required_nulls"))
        if not (has_falsifier or has_nulls):
            errors.append(
                f"{rel}: {line_id}: artifact is PASS but contract declares neither a "
                "falsifier nor required null baselines"
            )

    # --- artifact must be semantically honest in its own right ---
    errors.extend(truth_gate.evaluate_artifact(Path(artifact_rel), artifact))

    return errors


def check(repo_root: Path = ROOT) -> list[str]:
    """Evaluate every research-line contract graph; return all violations."""
    truth_gate = _load_truth_gate()
    violations: list[str] = []
    contracts = sorted((repo_root / "research_lines").glob("*/contract.yaml"))
    for contract_path in contracts:
        try:
            data = yaml.safe_load(contract_path.read_text(encoding="utf-8"))
        except (yaml.YAMLError, OSError) as exc:
            violations.append(f"{contract_path.as_posix()}: unreadable YAML ({exc})")
            continue
        violations.extend(evaluate_contract(contract_path, data, repo_root, truth_gate))
    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    args = parser.parse_args(argv)

    violations = check(args.repo_root)
    if violations:
        print("Claim-to-artifact graph gate FAILED:", file=sys.stderr)
        for v in violations:
            print(f"  ✗ {v}", file=sys.stderr)
        print(
            f"\n{len(violations)} broken proof-chain link(s). "
            "A claim above HYPOTHESIS must be backed end-to-end.",
            file=sys.stderr,
        )
        return 1
    print("Claim-to-artifact graph gate passed: every claim maps to an honest proof chain.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
