# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Aggregate every inference-integrity sub-verdict into one final verdict.

No single green workflow may imply system truth. This tool reads each substrate
artifact (coverage, mutable state, concurrency, causal prefix, runtime failure,
risk reservation, cache freshness, event-bus lifecycle) and — with ``--release``
— the release-gating artifacts (component strength, RVG). The final verdict is
PASS only when every consumed artifact is present, schema-valid, carries a passing
verdict, and is not a non-enforcing report-only run.

Exit code is fail-closed: a FAIL final verdict exits non-zero unless ``--report-only``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SCHEMA_ID = "geosync.final_inference_verdict.v1"

# Expected schema id each consumed artifact must declare. A wrong/unknown schema is
# a fail-closed condition (a renamed or unrelated file cannot masquerade as a
# sub-verdict). rvg is external tooling with its own contract; its schema id is
# not pinned here.
_SCHEMA_IDS: dict[str, str] = {
    "coverage_surface": "geosync.coverage_surface_report.v1",
    "mutable_state_registry": "geosync.mutable_state_registry.v1",
    "concurrency_matrix": "geosync.concurrency_matrix.v1",
    "causal_prefix_matrix": "geosync.causal_prefix_matrix.v1",
    "runtime_failure_matrix": "geosync.runtime_failure_matrix.v1",
    "risk_reservation_lifecycle": "geosync.risk_reservation_lifecycle.v1",
    "feature_cache_freshness": "geosync.feature_cache_freshness_matrix.v1",
    "event_bus_lifecycle": "geosync.event_bus_lifecycle_matrix.v1",
    "homeostasis_contract": "geosync.homeostasis_contract.v1",
    "inference_provenance": "geosync.inference_provenance.v1",
    "component_strength": "geosync.component_strength_report.v1",
}

# Each input: logical name, artifact path, schema id it must declare, the verdict
# values that count as a pass, and the tier (substrate = always; release = only
# under --release, because those artifacts are generated during the release run).
_PASS = ("PASS", "BOUND")
INPUTS: tuple[dict[str, Any], ...] = (
    {
        "name": "coverage_surface",
        "path": "artifacts/coverage_surface/coverage_surface_report.json",
        "pass_values": _PASS,
        "tier": "substrate",
    },
    {
        "name": "mutable_state_registry",
        "path": "artifacts/state/mutable_state_registry.json",
        "pass_values": _PASS,
        "tier": "substrate",
    },
    {
        "name": "concurrency_matrix",
        "path": "artifacts/concurrency/concurrency_matrix.json",
        "pass_values": _PASS,
        "tier": "substrate",
    },
    {
        "name": "causal_prefix_matrix",
        "path": "artifacts/time/causal_prefix_matrix.json",
        "pass_values": _PASS,
        "tier": "substrate",
    },
    {
        "name": "runtime_failure_matrix",
        "path": "artifacts/runtime_failure_matrix/runtime_failure_matrix.json",
        "pass_values": _PASS,
        "tier": "substrate",
    },
    {
        "name": "risk_reservation_lifecycle",
        "path": "artifacts/risk/reservation_lifecycle.json",
        "pass_values": _PASS,
        "tier": "substrate",
    },
    {
        "name": "feature_cache_freshness",
        "path": "artifacts/cache/feature_cache_freshness_matrix.json",
        "pass_values": _PASS,
        "tier": "substrate",
    },
    {
        "name": "event_bus_lifecycle",
        "path": "artifacts/messaging/event_bus_lifecycle_matrix.json",
        "pass_values": _PASS,
        "tier": "substrate",
    },
    {
        "name": "homeostasis_contract",
        "path": "artifacts/neuro/homeostasis_contract.json",
        "pass_values": ("PASS",),
        "tier": "substrate",
    },
    {
        "name": "inference_provenance",
        "path": "artifacts/provenance/inference_provenance.json",
        "pass_values": ("PASS",),
        "tier": "substrate",
    },
    {
        "name": "component_strength",
        "path": "artifacts/test_strength/component_strength_report.json",
        "pass_values": ("PASS",),
        "tier": "release",
    },
    {
        "name": "rvg_verdict",
        "path": "artifacts/rvg/RVG_VERDICT.json",
        "pass_values": _PASS,
        "tier": "release",
    },
)


def _item_passes(item: dict[str, Any]) -> bool:
    """Whether one nested row/invariant/check/ground/attack is passing."""

    verdict = item.get("verdict")
    if verdict is not None and verdict not in (
        "PASS",
        "BOUND",
        "ADMISSIBLE",
        "STABLE",
        "SYNCHRONISING",
        "GO",
    ):
        return False
    for boolean_field in ("passed", "holds", "defeated"):
        if boolean_field in item and item[boolean_field] is not True:
            return False
    return True


def _internally_consistent(data: dict[str, Any]) -> bool:
    """A PASS artifact must not hide a failing internal row/invariant/check.

    Closes the forge-the-top-verdict attack: an adversary who sets the top-level
    verdict to PASS while an internal item (matrix row, invariant, ground, attack)
    is FAIL/not-passed is caught here, because the aggregate re-reads the internal
    items rather than trusting the headline verdict.
    """

    for value in data.values():
        if not isinstance(value, list):
            continue
        for item in value:
            if isinstance(item, dict) and not _item_passes(item):
                return False
    return True


def _evaluate_input(spec: dict[str, Any], root: Path) -> dict[str, Any]:
    path = root / spec["path"]
    entry: dict[str, Any] = {
        "name": spec["name"],
        "path": spec["path"],
        "tier": spec["tier"],
        "present": path.is_file(),
        "verdict": None,
        "report_only": False,
        "passed": False,
        "reason": "",
    }
    if not entry["present"]:
        entry["reason"] = "artifact missing"
        return entry
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        entry["reason"] = f"unreadable artifact: {exc}"
        return entry
    expected_schema = _SCHEMA_IDS.get(spec["name"])
    if expected_schema is not None and data.get("schema") != expected_schema:
        entry["reason"] = f"schema {data.get('schema')!r} != expected {expected_schema!r}"
        return entry
    entry["verdict"] = data.get("verdict")
    entry["report_only"] = bool(data.get("report_only", False))
    if entry["report_only"]:
        entry["reason"] = "report_only run cannot satisfy the release gate"
        return entry
    if entry["verdict"] not in spec["pass_values"]:
        entry["reason"] = f"verdict {entry['verdict']!r} not in {spec['pass_values']}"
        return entry
    if not _internally_consistent(data):
        entry["reason"] = "internal inconsistency: a nested item fails while the verdict is PASS"
        return entry
    entry["passed"] = True
    return entry


def build_verdict(root: Path, *, release: bool) -> dict[str, Any]:
    """Aggregate the configured sub-verdicts into a final verdict document."""

    entries: list[dict[str, Any]] = []
    for spec in INPUTS:
        if spec["tier"] == "release" and not release:
            continue
        entries.append(_evaluate_input(spec, root))
    overall = "PASS" if entries and all(e["passed"] for e in entries) else "FAIL"
    return {
        "schema": SCHEMA_ID,
        "release": release,
        "inputs": entries,
        "verdict": overall,
    }


def exit_code(report: dict[str, Any], *, report_only: bool) -> int:
    if report["verdict"] == "FAIL" and not report_only:
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Final inference-integrity verdict aggregator")
    p.add_argument("--root", default=".", help="repository root holding the artifacts")
    p.add_argument(
        "--release",
        action="store_true",
        help="also require the release-gating artifacts (component strength, RVG)",
    )
    p.add_argument("--out", help="write the verdict JSON here (else stdout)")
    p.add_argument(
        "--report-only",
        action="store_true",
        help="non-enforcing: always exit 0 but stamp report_only=true",
    )
    args = p.parse_args(argv)

    report = build_verdict(Path(args.root), release=bool(args.release))
    report["report_only"] = bool(args.report_only)
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    print(f"final-inference verdict: {report['verdict']}", file=sys.stderr)
    return exit_code(report, report_only=bool(args.report_only))


if __name__ == "__main__":
    sys.exit(main())
