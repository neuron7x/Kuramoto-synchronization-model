#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Claim → evidence anchor compiler (audit task T4 of the 9.9 upgrade).

Reads ``research/systemic_risk/claims.yaml`` and asserts:

* every claim has ``id``, ``text``, ``status`` ∈ {verified, hypothesis, blocked}
* every claim has at least one ``evidence`` path that exists
* every claim has at least one ``falsifier`` entry
* every claim has a ``ci_gate`` value
* every ``evidence`` path resolves to a real file in the repo
* (with ``--fail-on-floating``) no claim has zero evidence anchors

Exits 0 on PASS, non-zero on FAIL. Used by the
``research-integrity-gate`` CI workflow.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
CLAIMS_PATH = REPO_ROOT / "research" / "systemic_risk" / "claims.yaml"

VALID_STATUSES: frozenset[str] = frozenset({"verified", "hypothesis", "blocked"})
REQUIRED_FIELDS: tuple[str, ...] = ("id", "text", "status", "evidence", "falsifier", "ci_gate")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="compile_claims.py",
        description="Validate research/systemic_risk/claims.yaml.",
    )
    parser.add_argument(
        "--fail-on-floating",
        action="store_true",
        help="Treat zero-evidence claims as fatal (default: warn).",
    )
    args = parser.parse_args(argv)

    if not CLAIMS_PATH.is_file():
        print(f"FAIL: {CLAIMS_PATH} not found")
        return 1
    with CLAIMS_PATH.open(encoding="utf-8") as fh:
        payload: Any = yaml.safe_load(fh)
    if not isinstance(payload, dict) or "claims" not in payload:
        print("FAIL: claims.yaml must be a mapping with top-level 'claims' key")
        return 1
    claims = payload["claims"]
    if not isinstance(claims, list) or not claims:
        print("FAIL: 'claims' must be a non-empty list")
        return 1

    issues: list[str] = []
    seen_ids: set[str] = set()
    for i, claim in enumerate(claims):
        if not isinstance(claim, dict):
            issues.append(f"claim #{i}: not a mapping")
            continue
        cid = claim.get("id", f"<#{i}>")
        if not isinstance(cid, str) or not cid:
            issues.append(f"claim #{i}: missing or non-string id")
        elif cid in seen_ids:
            issues.append(f"claim {cid}: duplicate id")
        else:
            seen_ids.add(cid)
        for field in REQUIRED_FIELDS:
            if field not in claim:
                issues.append(f"claim {cid}: missing required field {field!r}")
        status = claim.get("status")
        if status not in VALID_STATUSES:
            issues.append(f"claim {cid}: status {status!r} not in {sorted(VALID_STATUSES)}")
        evidence = claim.get("evidence", [])
        if not isinstance(evidence, list):
            issues.append(f"claim {cid}: evidence must be a list")
            evidence = []
        if not evidence:
            msg = f"claim {cid}: zero evidence anchors"
            if args.fail_on_floating:
                issues.append(msg)
            else:
                print(f"WARN: {msg}")
        for path_str in evidence:
            if not isinstance(path_str, str):
                issues.append(f"claim {cid}: evidence path must be string, got {path_str!r}")
                continue
            if not (REPO_ROOT / path_str).exists():
                issues.append(f"claim {cid}: evidence path does not exist: {path_str}")
        falsifier = claim.get("falsifier", [])
        if not isinstance(falsifier, list) or not falsifier:
            issues.append(f"claim {cid}: falsifier must be a non-empty list")
        ci_gate = claim.get("ci_gate")
        if not isinstance(ci_gate, str) or not ci_gate:
            issues.append(f"claim {cid}: missing ci_gate")

    if issues:
        print(f"FAIL: claims-compile audit ({len(issues)} issue(s))")
        for line in issues[:30]:
            print(f"  {line}")
        if len(issues) > 30:
            print(f"  ... {len(issues) - 30} more issue(s)")
        return 1
    print(f"PASS: {len(claims)} claims; all evidence paths resolve; all fields populated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
