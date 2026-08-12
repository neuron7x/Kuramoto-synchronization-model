#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Claim-maturity promotion gate (registry-driven).

The executable maturity ladder lives in
``analytics/signals/claim_maturity.py`` (``evaluate_promotion``). That module
is a pure decision function; this gate is the *registry* layer that runs it at
PR time over ``governance/CLAIM_MATURITY.yaml`` and fails closed.

For every registered claim the gate promotes it from ``UNOBSERVED`` to its
declared rung through the ladder and rejects it unless the cumulative evidence
for that rung and every rung below it is present — so no claim can skip a
state, promote synthetic evidence to a real-data rung, reach
ALTERNATIVES_ELIMINATED without a null + simpler-baseline comparison, or reach
BOUNDED_CLAIM_ALLOWED without the replay/provenance/falsifier/negative-evidence
conjunction. The registry layer additionally rejects forbidden
trading/alpha/profit language and any claim_boundary that is not the canonical
descriptor-only boundary.

Run::

    python scripts/ci/check_claim_maturity.py

Exit codes::

    0  — every registered claim's declared maturity is fully supported
    1  — a skipped state, missing evidence, silent promotion, or laundering
    2  — the registry itself is missing or malformed (fail-closed)
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "governance" / "CLAIM_MATURITY.yaml"
_LADDER_PATH = ROOT / "analytics" / "signals" / "claim_maturity.py"

# Language that would launder a structural descriptor into a market claim.
FORBIDDEN_TERMS: tuple[str, ...] = (
    "alpha",
    "profit",
    "trading signal",
    "buy signal",
    "sell signal",
    "guaranteed",
    "outperform",
    "financial advice",
)


def _load_ladder() -> Any:
    spec = importlib.util.spec_from_file_location("claim_maturity", _LADDER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load claim_maturity ladder module")
    module = importlib.util.module_from_spec(spec)
    sys.modules["claim_maturity"] = module
    spec.loader.exec_module(module)
    return module


def _check_claim(claim: dict[str, Any], ladder: Any) -> list[str]:
    failures: list[str] = []
    cid = str(claim.get("id", "<unnamed>"))
    declared = str(claim.get("maturity_state", ""))
    evidence = claim.get("evidence") or []
    if not isinstance(evidence, list):
        return [f"{cid}: 'evidence' must be a list of tokens"]

    if declared not in ladder.LADDER:
        return [f"{cid}: unknown maturity_state {declared!r}"]

    # Forbidden-language + boundary scan over the registry layer.
    boundary = claim.get("claim_boundary")
    if boundary not in (None, "") and str(boundary) != ladder.CLAIM_BOUNDARY:
        failures.append(f"{cid}: claim_boundary {boundary!r} != {ladder.CLAIM_BOUNDARY!r}")
    haystack = (str(claim.get("description", "")) + " " + " ".join(map(str, evidence))).lower()
    for term in FORBIDDEN_TERMS:
        if term in haystack:
            failures.append(
                f"{cid}: forbidden promotion language {term!r} (a descriptor is not a market claim)"
            )

    if declared == "UNOBSERVED":
        # Ground state: nothing to promote, nothing to prove.
        return failures

    try:
        verdict = ladder.evaluate_promotion("UNOBSERVED", declared, evidence)
    except ValueError as exc:
        failures.append(f"{cid}: rejected by ladder — {exc}")
        return failures

    if not verdict.allowed:
        gaps = ", ".join(f"{s}:{t}" for s, t in verdict.missing_evidence)
        failures.append(
            f"{cid}: declared {declared} unsupported — blocked at {verdict.blocked_at}; missing {gaps}"
        )
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=REGISTRY_PATH)
    args = parser.parse_args(argv)

    if not args.registry.is_file():
        print(f"FAIL: claim-maturity registry not found: {args.registry}", file=sys.stderr)
        return 2
    try:
        registry = yaml.safe_load(args.registry.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        print(f"FAIL: registry is not valid YAML: {exc}", file=sys.stderr)
        return 2
    if not isinstance(registry, dict):
        print("FAIL: registry root must be a mapping", file=sys.stderr)
        return 2
    claims = registry.get("claims")
    if not isinstance(claims, list) or not claims:
        print("FAIL: registry 'claims' must be a non-empty list", file=sys.stderr)
        return 2

    ladder = _load_ladder()
    any_failed = False
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        cid = str(claim.get("id", "<unnamed>"))
        failures = _check_claim(claim, ladder)
        mark = "PASS" if not failures else "FAIL"
        print(f"[{mark}] {cid} @ {claim.get('maturity_state', '?')}")
        for f in failures:
            print(f"       - {f}")
        any_failed = any_failed or bool(failures)

    n = len([c for c in claims if isinstance(c, dict)])
    if any_failed:
        print("\nFAIL: at least one claim declares an unsupported maturity", file=sys.stderr)
        return 1
    print(f"\nOK: all {n} claims sit at a fully-supported maturity rung")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
