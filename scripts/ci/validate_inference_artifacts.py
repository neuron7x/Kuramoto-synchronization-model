#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Validate every inference-integrity substrate artifact against its schema.

Stdlib + jsonschema only (no numpy / no pytest collection), so it runs in the
lean release-verdict workflow. Each artifact must exist, declare the expected
schema id, validate against that schema, and carry a passing verdict. Exits
non-zero on the first failure — fail-closed.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# artifact path -> schema path; both under the repo root.
_PAIRS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "artifacts/coverage_surface/coverage_surface_report.json",
        "audit/schema/coverage_surface_report.schema.json",
        ("PASS",),
    ),
    (
        "artifacts/state/mutable_state_registry.json",
        "audit/schema/mutable_state_registry.schema.json",
        ("BOUND",),
    ),
    (
        "artifacts/concurrency/concurrency_matrix.json",
        "audit/schema/concurrency_matrix.schema.json",
        ("PASS",),
    ),
    (
        "artifacts/time/causal_prefix_matrix.json",
        "audit/schema/causal_prefix_matrix.schema.json",
        ("PASS",),
    ),
    (
        "artifacts/runtime_failure_matrix/runtime_failure_matrix.json",
        "audit/schema/runtime_failure_matrix.schema.json",
        ("PASS",),
    ),
    (
        "artifacts/risk/reservation_lifecycle.json",
        "audit/schema/risk_reservation_lifecycle.schema.json",
        ("BOUND",),
    ),
    (
        "artifacts/cache/feature_cache_freshness_matrix.json",
        "audit/schema/feature_cache_freshness_matrix.schema.json",
        ("PASS",),
    ),
    (
        "artifacts/messaging/event_bus_lifecycle_matrix.json",
        "audit/schema/event_bus_lifecycle_matrix.schema.json",
        ("PASS",),
    ),
    (
        "artifacts/neuro/homeostasis_contract.json",
        "audit/schema/homeostasis_contract.schema.json",
        ("PASS",),
    ),
    (
        "artifacts/neuro/opponency_lyapunov.json",
        "audit/schema/opponency_lyapunov.schema.json",
        ("PASS",),
    ),
    (
        "artifacts/physics/kuramoto_synchrony.json",
        "audit/schema/kuramoto_synchrony.schema.json",
        ("PASS",),
    ),
    (
        "artifacts/inference/apparatus_transfer_report.json",
        "audit/schema/apparatus_transfer_report.schema.json",
        ("PASS",),
    ),
    (
        "artifacts/provenance/inference_provenance.json",
        "audit/schema/inference_provenance.schema.json",
        ("PASS",),
    ),
    (
        "artifacts/inference/final_inference_verdict.json",
        "audit/schema/final_inference_verdict.schema.json",
        ("PASS",),
    ),
    (
        "artifacts/inference/no_ungrounded_act.json",
        "audit/schema/no_ungrounded_act.schema.json",
        ("PASS",),
    ),
)


def main() -> int:
    import jsonschema

    failures: list[str] = []
    for artifact_rel, schema_rel, pass_values in _PAIRS:
        artifact_path = ROOT / artifact_rel
        schema_path = ROOT / schema_rel
        if not artifact_path.is_file():
            failures.append(f"{artifact_rel}: missing")
            continue
        if not schema_path.is_file():
            failures.append(f"{schema_rel}: missing schema")
            continue
        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        try:
            jsonschema.validate(artifact, schema)
        except jsonschema.ValidationError as exc:
            failures.append(f"{artifact_rel}: schema invalid: {exc.message}")
            continue
        if artifact.get("verdict") not in pass_values:
            failures.append(
                f"{artifact_rel}: verdict {artifact.get('verdict')!r} not in {pass_values}"
            )
        if artifact.get("report_only") is True:
            failures.append(f"{artifact_rel}: report_only run cannot gate release")

    if failures:
        for line in failures:
            print(f"FAIL {line}", file=sys.stderr)
        return 1
    print(f"validated {len(_PAIRS)} inference-integrity artifacts", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
