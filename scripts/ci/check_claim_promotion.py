#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Fail-closed tier-promotion gate (RES-020): a claim's self-declared `tier` in
docs/CLAIMS.yaml must have EARNED the executed audit verdict its tier demands.

First principle: "the right to assert ANCHORED" must be machine-earned, not
self-declared. geosync/proof/audit.py already collects and RUNS every claim's
falsifier and produces a per-claim verdict; this gate is a THIN CONSUMER of that
report. It NEVER re-runs a falsifier and never re-implements verdict logic:

  * verdict-strength ordering comes verbatim from geosync.proof.audit._SEVERITY
    (SUPPORTED > NOT_TESTED > DANGLING > REFUTED > FORBIDDEN_LANGUAGE);
  * staleness/tamper is caught with audit.verify_report() (recomputes the
    report's content_digest and re-hashes docs/CLAIMS.yaml) — the gate trusts
    the bytes on disk, not the author;
  * a --resolve-only report NEVER executes, so a resolved node is at best
    NOT_TESTED; the gate REFUSES to let that satisfy an ANCHORED (SUPPORTED)
    floor rather than laundering NOT_TESTED into a pass.

The tier -> minimum-verdict table, the evidence-path requirement, and the
documented heavy/optional-dep allowlist are policy-as-data in
claims/promotion_policy.yaml, pinned by sha256 in the output line. A claim whose
earned verdict is weaker than its (effective) tier floor is an OVER-PROMOTION
and fails the build closed (exit 1).

This is NOT the 14-rung maturity ladder (analytics/signals/claim_maturity.py /
governance/CLAIM_MATURITY.yaml): that governs self-declared evidence TOKENS over
a separate descriptor registry and never executes a test. This gate governs
EXECUTED verdicts over the real 27 docs/CLAIMS.yaml claims. They are not touched.

Usage:
    # 1) produce an EXECUTED report (default or --deep mode; NOT --resolve-only):
    python -m geosync.proof.audit
    # 2) enforce the promotion policy against it:
    python scripts/ci/check_claim_promotion.py

Exit codes:
    0  every claim's earned verdict meets its (effective) tier floor and every
       required evidence_path exists (allowlist relaxations applied and printed)
    1  over-promotion, refuted/dangling under a floor, a missing evidence_path,
       a stale/tampered report, a resolve-only report under a SUPPORTED floor,
       an invalid policy, a claim missing from the report, an unknown
       tier/verdict, or a stale/dead allowlist entry
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Callable

from geosync.proof.audit import (
    _SEVERITY,
    MODE_RESOLVE,
    NOT_TESTED,
    REFUTED,
    SUPPORTED,
    _sha256_file,
    load_claims,
    verify_report,
)

# The audit engine is the SINGLE SOURCE OF TRUTH for the verdict enum, the
# strength ordering, and report staleness verification. We import — never
# re-implement — all of it, and NEVER re-run a falsifier.
from geosync.proof.audit import (
    CLAIMS as AUDIT_CLAIMS,
)

ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / "claims" / "promotion_policy.yaml"
REPORT = ROOT / "artifacts" / "geosync_proof" / "audit.json"

# Hard contract minimums the policy DATA file may not weaken (compared by
# SEVERITY, not name, so a policy is free to be STRICTER). Instrument-invariant
# split: the table lives in editable data, but the floor-of-the-floor lives in
# code so editing the yaml can never launder ANCHORED below SUPPORTED.
_CONTRACT_MIN = {"ANCHORED": SUPPORTED, "EXTRAPOLATED": NOT_TESTED}

# The ONLY verdict an allowlist pardon may relax a floor to. NOT_TESTED admits an
# honestly-parked node but still excludes REFUTED (fired) and DANGLING
# (cannot-fire), so a pardon can never cover a broken falsifier.
_ALLOWLIST_RELAXED_FLOOR = NOT_TESTED

_VALID_FLOORS = frozenset(_SEVERITY) | {None}


# ---------------------------------------------------------------------------
# Policy loading + validation (fail-closed: a malformed policy is RED).
# ---------------------------------------------------------------------------
def load_policy(path: Path = POLICY) -> dict:
    import yaml

    obj = yaml.safe_load(path.read_text(encoding="utf-8"))
    return obj if isinstance(obj, dict) else {}


def validate_policy(policy: dict) -> list[str]:
    """Structural + hard-minimum validation. Returns problems (empty == valid)."""
    problems: list[str] = []

    # HARD CONTRACT MINIMUM (instrument-invariant split): evidence-path existence is
    # not a data-file knob the policy may disable. A claim resting on deleted evidence
    # is an over-promotion; allowing the editable YAML to set this false would be a
    # silent laundering vector (adversary-found). Present-but-falsy => INVALID policy.
    if "require_evidence_paths_exist" in policy and not policy["require_evidence_paths_exist"]:
        problems.append(
            "POLICY invalid: `require_evidence_paths_exist` may not be disabled — it is a "
            "hard contract minimum, not a data knob (a claim on deleted evidence is over-promotion)"
        )

    tier_floor = policy.get("tier_floor")
    if not isinstance(tier_floor, dict):
        problems.append("POLICY invalid: `tier_floor` missing or not a mapping")
        return problems

    for tier, floor in tier_floor.items():
        if floor not in _VALID_FLOORS:
            problems.append(
                f"POLICY invalid: tier {tier!r} floor {floor!r} is not an audit "
                f"verdict name (or null)"
            )

    # hard contract minimums — the data file may equal or strengthen, not weaken.
    for tier, hard in _CONTRACT_MIN.items():
        floor = tier_floor.get(tier)
        if floor is None or floor not in _SEVERITY:
            problems.append(
                f"POLICY invalid: tier {tier!r} must declare a floor >= {hard} "
                f"(contract minimum); got {floor!r}"
            )
            continue
        if _SEVERITY[floor] < _SEVERITY[hard]:
            problems.append(
                f"POLICY invalid: tier {tier!r} floor {floor} is WEAKER than the "
                f"contract minimum {hard} — cannot weaken via the data file"
            )

    allowlist = policy.get("allowlist", {}) or {}
    if not isinstance(allowlist, dict):
        problems.append("POLICY invalid: `allowlist` must be a mapping if present")
        allowlist = {}
    for cid, entry in allowlist.items():
        if not isinstance(entry, dict):
            problems.append(f"POLICY invalid: allowlist[{cid!r}] must be a mapping")
            continue
        relaxed = entry.get("relaxed_floor")
        if relaxed != _ALLOWLIST_RELAXED_FLOOR:
            problems.append(
                f"POLICY invalid: allowlist[{cid!r}].relaxed_floor must be exactly "
                f"{_ALLOWLIST_RELAXED_FLOOR} (a pardon may never admit REFUTED/DANGLING); "
                f"got {relaxed!r}"
            )
        reason = str(entry.get("reason", "")).strip()
        if not reason:
            problems.append(
                f"POLICY invalid: allowlist[{cid!r}] must carry a non-empty `reason` "
                f"(a pardon is never silent)"
            )
    return problems


# ---------------------------------------------------------------------------
# Pure evaluation core (dependency-injected for teeth; no disk, no subprocess).
# ---------------------------------------------------------------------------
def evaluate(
    policy: dict,
    report: dict,
    claims: list[dict],
    path_exists: Callable[[str], bool],
    severity: dict[str, int] = _SEVERITY,
) -> dict:
    """Compare every claim's EARNED verdict to its (effective) tier floor.

    Deterministic: no wall-clock, no subprocess, all I/O injected via
    ``path_exists``. ``claims`` is the authoritative, source-ordered list from
    docs/CLAIMS.yaml (supplies the id set + evidence_paths); ``report`` supplies
    the engine-derived tier + EXECUTED verdict per claim. Returns
    ``{"ok", "violations", "applied", "checked"}``.
    """
    violations: list[str] = []
    applied: list[str] = []

    tier_floor = policy.get("tier_floor", {})
    allowlist = policy.get("allowlist", {}) or {}
    # Default True (fail-closed): an ABSENT key must not silently disable the check.
    # validate_policy additionally rejects a policy that sets it explicitly falsy, so both
    # the delete-the-line and set-false laundering vectors are closed.
    require_ev = bool(policy.get("require_evidence_paths_exist", True))
    mode = str(report.get("mode", ""))
    rows = {str(r.get("id")): r for r in report.get("claims", []) if isinstance(r, dict)}

    claims_by_id = {str(c.get("id")): c for c in claims}
    claim_ids = [str(c.get("id")) for c in claims]

    # dead allowlist entry: pardons a claim that does not exist -> RED (drift).
    for aid in allowlist:
        if aid not in claims_by_id:
            violations.append(
                f"DEAD-ALLOWLIST policy pardons unknown claim {aid!r} "
                f"(absent from docs/CLAIMS.yaml)"
            )

    supported_floor_demanded = False

    for cid in claim_ids:
        row = rows.get(cid)
        if row is None:
            violations.append(
                f"MISSING claim {cid!r} is absent from the audit report "
                f"(stale report — re-run the audit engine)"
            )
            continue

        tier = str(row.get("tier", ""))
        verdict = str(row.get("verdict", ""))

        if verdict not in severity:
            violations.append(
                f"UNKNOWN-VERDICT claim {cid!r} has verdict {verdict!r} not in the "
                f"audit severity table"
            )
            continue
        if tier not in tier_floor:
            violations.append(
                f"UNKNOWN-TIER claim {cid!r} tier {tier!r} has no promotion-policy floor"
            )
            continue

        tier_floor_name = tier_floor[tier]
        earned = severity[verdict]

        entry = allowlist.get(cid)
        eff_floor_name = _ALLOWLIST_RELAXED_FLOOR if entry is not None else tier_floor_name

        if eff_floor_name is not None and severity[eff_floor_name] >= severity[SUPPORTED]:
            supported_floor_demanded = True

        # [1] over-promotion: earned verdict weaker than the (effective) floor.
        if eff_floor_name is not None and earned < severity[eff_floor_name]:
            if verdict == REFUTED:
                # loudest signal: a FIRED falsifier means the assertion is false.
                violations.append(
                    f"OVER-PROMOTION claim {cid!r} declares tier {tier} but its "
                    f"falsifier FIRED (REFUTED); demote or RETIRE the claim"
                )
            else:
                floor_src = "allowlist-relaxed floor" if entry is not None else "tier floor"
                violations.append(
                    f"OVER-PROMOTION claim {cid!r} declares tier {tier} but earned "
                    f"{verdict} (< {floor_src} {eff_floor_name})"
                )
            continue

        # [2] stale pardon: an allowlisted claim that now meets its UNRELAXED tier
        # floor no longer needs the pardon -> RED, force removal (never silent).
        if (
            entry is not None
            and tier_floor_name is not None
            and earned >= severity[tier_floor_name]
        ):
            violations.append(
                f"STALE-ALLOWLIST claim {cid!r} now earns {verdict} which meets its "
                f"tier floor {tier_floor_name}; remove the promotion_policy allowlist entry"
            )
            continue

        # [3] evidence-path existence for promoted (floored) tiers. A claim resting
        # on deleted evidence is an over-promotion regardless of its verdict.
        if require_ev and tier_floor_name is not None:
            claim = claims_by_id.get(cid, {})
            for p in claim.get("evidence_paths", []) or []:
                if not path_exists(str(p)):
                    violations.append(
                        f"MISSING-EVIDENCE claim {cid!r} (tier {tier}) declares "
                        f"evidence_path that does not exist: {p}"
                    )

        if entry is not None:
            applied.append(
                f"{cid}: parked at {verdict} (floor relaxed to {eff_floor_name}) "
                f"— {str(entry.get('reason', '')).strip()}"
            )

    # [4] mode: a resolve-only report can never earn SUPPORTED. Emit ONE clear
    # reason instead of drowning the operator in per-claim over-promotions.
    if mode == MODE_RESOLVE and supported_floor_demanded:
        violations.append(
            "MODE resolve-only report cannot earn SUPPORTED, so a SUPPORTED tier "
            "floor is unsatisfiable. Run `python -m geosync.proof.audit` "
            "(default or --deep) before this gate."
        )

    return {
        "ok": not violations,
        "violations": violations,
        "applied": applied,
        "checked": len(claim_ids),
    }


# ---------------------------------------------------------------------------
# Thin CLI: load + verify + evaluate + report. All disk I/O lives here.
# ---------------------------------------------------------------------------
def _real_path_exists(rel: str) -> bool:
    return (ROOT / rel).exists()


def run(report_path: Path, policy_path: Path, claims_path: Path) -> tuple[int, list[str]]:
    if not policy_path.exists():
        return 1, [f"POLICY not found: {policy_path}"]
    if not report_path.exists():
        return 1, [
            f"REPORT not found: {report_path}. Run `python -m geosync.proof.audit` "
            f"(default or --deep) first."
        ]

    policy = load_policy(policy_path)
    problems = validate_policy(policy)
    if problems:
        return 1, problems

    # staleness/tamper: trust the bytes, not the author.
    ok, verify_problems = verify_report(report_path)
    if not ok:
        return 1, [f"REPORT stale/tampered ({report_path}):"] + verify_problems

    report = json.loads(report_path.read_text(encoding="utf-8"))
    claims = load_claims(claims_path)

    result = evaluate(policy, report, claims, _real_path_exists)
    policy_sha = _sha256_file(policy_path)

    lines: list[str] = []
    for note in result["applied"]:
        lines.append(f"  allowlist-applied {note}")
    lines += result["violations"]
    lines.append(
        "GEOSYNC_PROMOTION "
        f"ok={result['ok']} "
        f"mode={report.get('mode')} "
        f"checked={result['checked']} "
        f"violations={len(result['violations'])} "
        f"allowlisted={len(result['applied'])} "
        f"policy_sha256={policy_sha} "
        f"report={report_path.name}"
    )
    return (0 if result["ok"] else 1), lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="check_claim_promotion",
        description=(
            "Fail-closed tier-promotion gate (RES-020): every docs/CLAIMS.yaml tier "
            "must have EARNED the audit verdict claims/promotion_policy.yaml demands. "
            "Consumes geosync.proof.audit's executed verdicts; never re-runs a falsifier."
        ),
    )
    parser.add_argument("--report", type=Path, default=REPORT, help="audit.json to enforce")
    parser.add_argument("--policy", type=Path, default=POLICY, help="promotion policy yaml")
    parser.add_argument(
        "--claims", type=Path, default=AUDIT_CLAIMS, help="docs/CLAIMS.yaml (id source of truth)"
    )
    args = parser.parse_args(argv)

    code, lines = run(args.report, args.policy, args.claims)
    stream = sys.stdout if code == 0 else sys.stderr
    for line in lines:
        stream.write(line + "\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
