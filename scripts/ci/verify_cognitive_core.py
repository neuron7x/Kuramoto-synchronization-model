#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Self-verifying meta-gate — one signed verdict over the whole cognitive core.

The cognitive core is verified by many independent layers (executable laws,
soundness, parameter- and code-mutation, property/metamorphic/convergence/oracle
checks, runtime enforcement, calibration). This meta-gate composes their static
contract state into ONE deterministic, content-addressed verdict so a single
command answers "is the invariant centre intact?".

It checks, fail-closed:
  * every blocking falsification law carries a collected positive witness AND a
    collected negative control (via core.physics.governance.promotion_gate);
  * the mutation-kill baseline floors are well-formed and the cognitive core is
    registered at a 1.0 floor;
and emits ``evidence/physics/cognitive_core_verdict.json`` with a SHA-256 over the
canonical verdict body. Exit 0 iff GREEN.

    python scripts/ci/verify_cognitive_core.py            # verify + emit verdict
    python scripts/ci/verify_cognitive_core.py --check    # verify without writing
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "physics_contracts" / "falsification_catalog.yaml"
BASELINE = ROOT / "docs" / "MUTATION_KILL_BASELINE.json"
VERDICT = ROOT / "evidence" / "physics" / "cognitive_core_verdict.json"
CORE_MODULE = "core/physics/cognitive_core.py"


def _verdict_body() -> dict[str, Any]:
    """Compose the deterministic verdict body (no timestamps, no RNG)."""
    from core.physics.governance import (
        check_negative_controls,
        check_witness_coverage,
        load_catalog,
        promotion_gate,
    )

    catalog = load_catalog(CATALOG)
    gate = promotion_gate(catalog, ROOT, require_evidence=False)
    missing_pos = sorted(check_witness_coverage(catalog, ROOT))
    missing_neg = sorted(check_negative_controls(catalog, ROOT))

    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    modules = baseline.get("modules", {})
    core_floor = float(modules.get(CORE_MODULE, {}).get("floor", 0.0))
    bad_floors = sorted(
        m for m, s in modules.items() if not (0.0 <= float(s.get("floor", -1.0)) <= 1.0)
    )

    checks = {
        "all_laws_witnessed": gate["status"] == "PASS",
        "no_missing_positive_witness": missing_pos == [],
        "no_missing_negative_control": missing_neg == [],
        "cognitive_core_mutation_floor_full": core_floor == 1.0,
        "mutation_floors_well_formed": bad_floors == [],
    }
    return {
        "schema": "geosync.cognitive_core_verdict.v1",
        "n_laws": int(gate["n_laws"]),
        "n_blocking": int(gate["n_blocking"]),
        "mutation_modules": sorted(modules),
        "cognitive_core_mutation_floor": core_floor,
        "checks": checks,
        "missing_positive_witness": missing_pos,
        "missing_negative_control": missing_neg,
        "verdict": "GREEN" if all(checks.values()) else "RED",
    }


def verify() -> dict[str, Any]:
    """Return the full verdict including its content hash."""
    body = _verdict_body()
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    body_hash = hashlib.sha256(canonical).hexdigest()
    return {**body, "verdict_sha256": body_hash}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="verify without writing the verdict")
    args = parser.parse_args(argv)

    result = verify()
    if not args.check:
        VERDICT.parent.mkdir(parents=True, exist_ok=True)
        VERDICT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(
        f"COGNITIVE-CORE META-GATE: {result['verdict']} "
        f"({result['n_blocking']} blocking laws, core mutation floor "
        f"{result['cognitive_core_mutation_floor']:.2f}, sha256 {result['verdict_sha256'][:12]})"
    )
    if result["verdict"] != "GREEN":
        for name, ok in result["checks"].items():
            if not ok:
                print(f"  FAILED CHECK: {name}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
