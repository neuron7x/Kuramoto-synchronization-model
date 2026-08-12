# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Fail-closed gate over the RES-010 power / effect-size / uncertainty report.

The flagship RQ (FLAGSHIP-RQ-001) has an *integer defect-count* outcome, not a
market return. A power/uncertainty report for it is only honest if it (a) leads
with an effect size and an interval rather than a bare p-value, (b) declares a
machine-readable power/adequacy verdict, and (c) never emits a binary
SUPPORTED/REJECTED claim off the back of an underpowered result.

This gate refuses to let that report degrade into a bare-p-value claim, a
binary verdict smuggled past an underpowered flag, or a missing power gate.

RED (non-zero) iff ANY of:

  1. BINARY-WHILE-UNDERPOWERED -- a binary SUPPORTED/REJECTED (or equivalent)
     claim is present while the analysis is flagged ``underpowered: true``.
  2. NO EFFECT-SIZE + INTERVAL -- the report lacks a point effect-size estimate
     or lacks at least one interval carrying numeric lower/upper bounds.
  3. POWER FIELD MISSING -- the ``power_adequacy`` block (with its ``power_gate``
     and ``underpowered`` fields) is absent.
  4. BINARY-WHILE-UNREPRODUCIBLE -- a binary SUPPORTED claim while the
     same-snapshot reproducibility leg is unverified (RES-008 consistency guard).

Exit codes::

    0  -- effect-size + interval led, power gate present, no illegitimate binary
    1  -- a policy violation (one of the RED conditions above)
    2  -- the report file is absent or malformed (fail-closed)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
REPORT_PATH = ROOT / "artifacts" / "research" / "power_uq_report.json"
# RES-008 source of record for the flagship study — the reproducibility flag and
# verdict live here, NOT in this report. The gate cross-checks against it so an
# author cannot self-declare reproducibility_verified_at_S=true to smuggle a
# binary claim past this gate (hardening from the RES-007/RES-010 review).
COMPARISON_PATH = ROOT / "benchmarks" / "flagship_baselines" / "comparison_report.json"

# Tokens that constitute a *binary* research verdict. INSUFFICIENT_EVIDENCE,
# WITHHELD, and null are explicitly NOT binary.
BINARY_TOKENS = frozenset(
    {
        "SUPPORTED",
        "REJECTED",
        "PROVEN",
        "DISPROVEN",
        "CONFIRMED",
        "REFUTED",
        "PASS_FLAGSHIP",
        "HARD_PASS",
        "HARD_FAIL",
    }
)

# Fields whose value, if it is a binary token, counts as a binary claim.
VERDICT_FIELDS = ("binary_verdict", "verdict", "claim", "conclusion")


class GateError(Exception):
    """Malformed / missing input -- maps to exit code 2 (fail-closed)."""


def _load_json(path: Path) -> Any:
    if not path.exists():
        raise GateError(f"missing required file: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise GateError(f"malformed JSON in {path}: {exc}") from exc


def _binary_claim_present(report: dict[str, Any]) -> bool:
    """True iff any recognised verdict field carries a binary token."""
    for field in VERDICT_FIELDS:
        value = report.get(field)
        if isinstance(value, str) and value.strip().upper() in BINARY_TOKENS:
            return True
    return False


def _has_effect_size(report: dict[str, Any]) -> bool:
    eff = report.get("effect_size")
    if not isinstance(eff, dict):
        return False
    return eff.get("point_estimate") is not None


def _has_interval(report: dict[str, Any]) -> bool:
    intervals = report.get("intervals")
    if not isinstance(intervals, list) or not intervals:
        return False
    for iv in intervals:
        if not isinstance(iv, dict):
            continue
        lo, hi = iv.get("lower"), iv.get("upper")
        if isinstance(lo, (int, float)) and isinstance(hi, (int, float)):
            return True
    return False


def _is_underpowered(report: dict[str, Any]) -> bool:
    pa = report.get("power_adequacy")
    if isinstance(pa, dict) and isinstance(pa.get("underpowered"), bool):
        return pa["underpowered"]
    # If unreadable, treat as underpowered (fail-closed).
    return True


def _power_field_present(report: dict[str, Any]) -> bool:
    pa = report.get("power_adequacy")
    if not isinstance(pa, dict):
        return False
    return ("power_gate" in pa) and ("underpowered" in pa)


def _reproducibility_verified(report: dict[str, Any]) -> bool:
    rc = report.get("reproducibility_caveat")
    if isinstance(rc, dict):
        return bool(rc.get("reproducibility_verified_at_S", False))
    return False


def _res008_reproducibility_verified() -> bool:
    """Reproducibility flag from the RES-008 source of record. Fail-closed: an
    unreadable/absent SSOT is treated as NOT verified."""
    try:
        doc = _load_json(COMPARISON_PATH)
    except Exception:
        return False
    if isinstance(doc, dict):
        return bool(doc.get("reproducibility_verified_at_S", False))
    return False


def evaluate(report: dict[str, Any]) -> dict[str, Any]:
    """Pure evaluation over an already-loaded report dict."""
    problems: list[str] = []

    power_present = _power_field_present(report)
    if not power_present:
        problems.append(
            "power gate field missing: report has no 'power_adequacy' block with "
            "'power_gate' and 'underpowered' fields"
        )

    has_eff = _has_effect_size(report)
    has_iv = _has_interval(report)
    if not has_eff:
        problems.append(
            "no effect-size reported: 'effect_size.point_estimate' is absent"
        )
    if not has_iv:
        problems.append(
            "no interval reported: 'intervals' lacks an entry with numeric "
            "lower/upper bounds"
        )

    binary = _binary_claim_present(report)
    underpowered = _is_underpowered(report)
    if binary and underpowered:
        problems.append(
            "binary claim from an underpowered result: a binary SUPPORTED/REJECTED "
            "verdict is present while power_adequacy.underpowered is true"
        )

    if binary and not _reproducibility_verified(report):
        problems.append(
            "binary claim while same-snapshot reproducibility is unverified "
            "(reproducibility_verified_at_S is not true) -- RES-008 consistency guard"
        )

    # Hardening: the report's self-declared reproducibility flag may not exceed
    # the RES-008 source of record. If the report claims verified but the SSOT
    # does not, RED — a falsified flag cannot smuggle a binary claim past this.
    if _reproducibility_verified(report) and not _res008_reproducibility_verified():
        problems.append(
            "report declares reproducibility_verified_at_S=true but the RES-008 "
            "source of record (comparison_report.json) does not -- self-declared "
            "reproducibility cannot exceed the SSOT (fail-closed)"
        )

    return {
        "report_path": str(REPORT_PATH),
        "power_field_present": power_present,
        "has_effect_size": has_eff,
        "has_interval": has_iv,
        "binary_claim_present": binary,
        "underpowered": underpowered,
        "reproducibility_verified_at_S": _reproducibility_verified(report),
        "problems": problems,
        "ok": not problems,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit machine-readable verdict")
    args = parser.parse_args(argv)

    try:
        report = _load_json(REPORT_PATH)
        if not isinstance(report, dict):
            raise GateError("report is not a JSON object")
        verdict = evaluate(report)
    except GateError as exc:
        if args.json:
            print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        else:
            print(f"POWER-UQ GATE: MALFORMED -- {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(verdict, indent=2, sort_keys=True))
    elif verdict["ok"]:
        print(
            "POWER-UQ GATE: PASS -- effect-size + interval led, power gate present "
            f"(underpowered={verdict['underpowered']}), no illegitimate binary claim."
        )
    else:
        print("POWER-UQ GATE: FAIL", file=sys.stderr)
        for problem in verdict["problems"]:
            print(f"  - {problem}", file=sys.stderr)

    return 0 if verdict["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
