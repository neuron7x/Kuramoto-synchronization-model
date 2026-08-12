#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Deterministic readiness gate for AAR-PRO-V1 / DRO-ARA.

This script is intentionally stricter than the smoke example: it proves the
runtime modules compile, rejects the historic truncation/synthetic-chronology
regressions, verifies comparator precision numerically, and executes a real
``geosync_observe`` pass to confirm circuit-breaker output wiring.
"""

from __future__ import annotations

import json
import math
import py_compile
import sys
from pathlib import Path
from typing import Any

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.dro_ara import geosync_observe
from geosync_hpc.control import (
    ExpectedResultModel,
    ObservedActionResult,
    accept_action_result,
)

ENGINE = REPO_ROOT / "core" / "dro_ara" / "engine.py"
COMPARATOR = REPO_ROOT / "geosync_hpc" / "control" / "action_result_comparator.py"
SELF_HEALING = REPO_ROOT / "geosync_hpc" / "control" / "self_healing.py"
SMOKE = REPO_ROOT / "scripts" / "aar_pro_smoke.py"


def _check_syntax() -> list[str]:
    compiled: list[str] = []
    for path in (ENGINE, COMPARATOR, SELF_HEALING, SMOKE):
        py_compile.compile(str(path), doraise=True)
        compiled.append(str(path.relative_to(REPO_ROOT)))
    return compiled


def _check_source_guards() -> None:
    source = ENGINE.read_text(encoding="utf-8")
    forbidden = ("return round(f  <--", "return round(f\n", "return wi\n", "3 * step_index")
    for token in forbidden:
        if token in source:
            raise SystemExit(f"AAR_PRO_READINESS_FAIL: forbidden source token present: {token}")
    required = (
        "return round(float(np.mean(a.variational_energy[-STABLE_RUNS:])), 6)",
        "chronology = _CausalChronology()",
        "circuit_breaker = free_energy > dynamic_free_energy_threshold",
        '"causal_chronology_hash": chronology_hash',
    )
    for token in required:
        if token not in source:
            raise SystemExit(f"AAR_PRO_READINESS_FAIL: required source token missing: {token}")


def _check_precision_distance() -> float:
    expected = ExpectedResultModel(
        action_id="readiness-precision",
        action_type="readiness",
        expected_result=(0.0, 0.0),
        expected_result_variance=(1.0, 4.0),
        context_signature=(0.0,),
        model_created_seq=1,
        action_started_seq=2,
        error_threshold=10.0,
        rollback_threshold=20.0,
    )
    observed = ObservedActionResult(
        action_id="readiness-precision",
        observed_seq=3,
        observed_result=(1.0, 4.0),
        reverse_afferentation_present=True,
    )
    witness = accept_action_result(expected, observed)
    value = witness.precision_weighted_outcome_error
    if value is None or not math.isclose(value, math.sqrt(5.0), abs_tol=1e-9):
        raise SystemExit(f"AAR_PRO_READINESS_FAIL: bad precision distance: {value}")
    return round(value, 12)


def _deterministic_price() -> np.ndarray:
    steps = np.arange(640, dtype=np.float64)
    return 100.0 + 0.02 * steps + 0.5 * np.sin(steps / 17.0) + 0.1 * np.cos(steps / 7.0)


def _check_observer() -> dict[str, Any]:
    verdict = geosync_observe(_deterministic_price(), window=256, step=64)
    required = {
        "free_energy",
        "free_energy_circuit_breaker",
        "dynamic_free_energy_threshold",
        "belief_mean",
        "belief_variance",
        "causal_chronology_hash",
        "recovery_action",
        "regime",
        "risk_scalar",
        "signal",
    }
    missing = required - verdict.keys()
    if missing:
        raise SystemExit(f"AAR_PRO_READINESS_FAIL: missing observer keys: {sorted(missing)}")
    if len(verdict["causal_chronology_hash"]) != 64:
        raise SystemExit("AAR_PRO_READINESS_FAIL: chronology hash must be 64 hex chars")
    if not (0.05 <= verdict["dynamic_free_energy_threshold"] <= 2.0):
        raise SystemExit("AAR_PRO_READINESS_FAIL: dynamic threshold outside bounded range")
    if verdict["belief_variance"] <= 0.0:
        raise SystemExit("AAR_PRO_READINESS_FAIL: belief variance must stay positive")
    if verdict["free_energy_circuit_breaker"]:
        if (
            verdict["regime"] != "INVALID"
            or verdict["signal"] != "REDUCE"
            or verdict["risk_scalar"] != 0.0
        ):
            raise SystemExit("AAR_PRO_READINESS_FAIL: circuit breaker did not force INVALID/REDUCE/0")
        if verdict["recovery_action"] != "REDUCE_RISK":
            raise SystemExit("AAR_PRO_READINESS_FAIL: breaker must emit REDUCE_RISK")
    if verdict["recovery_action"] not in {"ALLOW_MODEL_UPDATE", "EXPAND_CONTEXT", "REDUCE_RISK"}:
        raise SystemExit("AAR_PRO_READINESS_FAIL: unknown recovery action")
    return verdict


def main() -> None:
    compiled = _check_syntax()
    _check_source_guards()
    precision = _check_precision_distance()
    verdict = _check_observer()
    output = {
        "schema_version": "AAR-PRO-V1-READINESS",
        "compiled": compiled,
        "precision_weighted_distance": precision,
        "observer": {
            "free_energy": verdict["free_energy"],
            "free_energy_circuit_breaker": verdict["free_energy_circuit_breaker"],
            "dynamic_free_energy_threshold": verdict["dynamic_free_energy_threshold"],
            "belief_variance": verdict["belief_variance"],
            "causal_chronology_hash": verdict["causal_chronology_hash"],
            "recovery_action": verdict["recovery_action"],
            "regime": verdict["regime"],
            "risk_scalar": verdict["risk_scalar"],
            "signal": verdict["signal"],
        },
        "status": "READY",
    }
    print(json.dumps(output, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
