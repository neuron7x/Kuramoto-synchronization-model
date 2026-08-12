# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Fail-closed gate over the FLAGSHIP-RQ-001 baseline hierarchy.

The flagship claim is only meaningful against a COMPLETE hierarchy of real,
runnable comparators and a comparison that applies the PREREGISTERED decision
rule. This gate refuses to let that hierarchy rot into stubs or a self-serving
verdict. It verifies:

1. COMPLETE HIERARCHY -- every required baseline tier (NAIVE, EXISTING_SUITE,
   ABLATED, SHUFFLED) is declared in ``hierarchy.yaml``, is a real callable in
   ``baselines.py``, and appears in ``comparison_report.json``. A flagship entry
   is present too.
2. EACH BASELINE DEFINED -- each tier maps to an importable, callable function
   (not a stub / not missing).
3. PREREG RULE APPLIED -- the report's ``verdict`` equals a fresh re-derivation
   via ``baselines.decide`` from the report's OWN numbers. This catches a report
   that claims SUPPORTED without meeting the preregistered margin, or without the
   reproducibility leg -- the exact tampering the gate exists to detect.

Exit codes::

    0  -- hierarchy complete, baselines defined, verdict matches the prereg rule
    1  -- an incompleteness / a verdict that violates the prereg rule
    2  -- a required file is absent or malformed (fail-closed)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
BASELINES_DIR = ROOT / "benchmarks" / "flagship_baselines"
HIERARCHY_YAML = BASELINES_DIR / "hierarchy.yaml"
COMPARISON_REPORT = BASELINES_DIR / "comparison_report.json"



class GateError(Exception):
    """Malformed / missing input -- maps to exit code 2 (fail-closed)."""


def _load_yaml(path: Path) -> Any:
    if not path.exists():
        raise GateError(f"missing required file: {path}")
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:  # pragma: no cover - defensive
        raise GateError(f"malformed YAML in {path}: {exc}") from exc


def _load_json(path: Path) -> Any:
    if not path.exists():
        raise GateError(f"missing required file: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise GateError(f"malformed JSON in {path}: {exc}") from exc


def evaluate() -> dict[str, Any]:
    """Return a machine-readable verdict for the baseline hierarchy.

    Raises GateError (exit 2) on missing/malformed files.
    """
    try:
        # Load by file location — no sys.path mutation (import-architecture ratchet).
        import importlib.util as _ilu

        _sp = _ilu.spec_from_file_location(
            "_flagship_baselines", BASELINES_DIR / "baselines.py"
        )
        assert _sp and _sp.loader
        B = _ilu.module_from_spec(_sp)
        sys.modules["_flagship_baselines"] = B  # register before exec (dataclasses needs it)
        _sp.loader.exec_module(B)
    except (ImportError, FileNotFoundError, AssertionError) as exc:  # pragma: no cover - defensive
        raise GateError(f"cannot import baselines module: {exc}") from exc

    hierarchy = _load_yaml(HIERARCHY_YAML)
    if not isinstance(hierarchy, dict):
        raise GateError("hierarchy.yaml must parse to a mapping")
    report = _load_json(COMPARISON_REPORT)
    if not isinstance(report, dict):
        raise GateError("comparison_report.json must parse to a mapping")

    problems: list[str] = []

    # --- (1) + (2) complete hierarchy, each baseline a real callable --------- #
    declared_tiers = {
        str(b.get("tier")) for b in hierarchy.get("baselines", []) if isinstance(b, dict)
    }
    report_tiers = set(report.get("baselines", {}).keys())

    for tier in B.REQUIRED_TIERS:
        if tier not in declared_tiers:
            problems.append(f"hierarchy.yaml: required baseline tier '{tier}' not declared")
        if tier not in report_tiers:
            problems.append(f"comparison_report.json: tier '{tier}' missing from baselines")
        spec = B.BASELINES.get(tier)
        if spec is None or not callable(spec.fn):
            problems.append(f"baselines.py: tier '{tier}' has no callable definition (stub?)")

    # Flagship comparator must be present in report + registry.
    if B.FLAGSHIP_NAME not in report:
        problems.append(f"comparison_report.json: missing '{B.FLAGSHIP_NAME}' entry")
    if not callable(getattr(B, "flagship_check", None)):
        problems.append("baselines.py: flagship_check is not callable")

    # Every reported baseline must carry an integer D (a real measurement).
    for tier, entry in report.get("baselines", {}).items():
        if not isinstance(entry, dict) or not isinstance(entry.get("D"), int):
            problems.append(f"comparison_report.json: baseline '{tier}' has no integer D")

    # --- (3) prereg decision rule actually applied --------------------------- #
    required_report_keys = (
        "D_marginal",
        "reproducibility_verified_at_S",
        "marginal_detection_confirmed",
        "prereg_margin",
        "verdict",
    )
    missing = [k for k in required_report_keys if k not in report]
    rederived: str | None = None
    if missing:
        problems.append(
            "comparison_report.json: missing keys required to re-derive verdict: "
            + ", ".join(missing)
        )
    else:
        try:
            rederived = B.decide(
                d_marginal=int(report["D_marginal"]),
                reproducibility_verified=bool(report["reproducibility_verified_at_S"]),
                marginal_detection_confirmed=bool(report["marginal_detection_confirmed"]),
                prereg_margin=int(report["prereg_margin"]),
            )
        except (ValueError, TypeError) as exc:
            problems.append(f"comparison_report.json: verdict re-derivation failed: {exc}")
        else:
            if rederived != report["verdict"]:
                problems.append(
                    f"comparison_report.json: verdict '{report['verdict']}' does NOT match the "
                    f"preregistered rule (re-derived '{rederived}' from D_marginal="
                    f"{report['D_marginal']}, reproducible={report['reproducibility_verified_at_S']})"
                )

    return {
        "required_tiers": list(B.REQUIRED_TIERS),
        "declared_tiers": sorted(declared_tiers),
        "report_tiers": sorted(report_tiers),
        "report_verdict": report.get("verdict"),
        "rederived_verdict": rederived,
        "problems": problems,
        "ok": not problems,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit machine-readable verdict")
    args = parser.parse_args(argv)

    try:
        verdict = evaluate()
    except GateError as exc:
        if args.json:
            print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        else:
            print(f"BASELINE GATE: MALFORMED -- {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(verdict, indent=2, sort_keys=True))
    elif verdict["ok"]:
        print(
            f"BASELINE GATE: PASS -- hierarchy complete "
            f"({len(verdict['required_tiers'])} tiers), verdict "
            f"'{verdict['report_verdict']}' matches the preregistered rule."
        )
    else:
        print("BASELINE GATE: FAIL", file=sys.stderr)
        for problem in verdict["problems"]:
            print(f"  - {problem}", file=sys.stderr)

    return 0 if verdict["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
