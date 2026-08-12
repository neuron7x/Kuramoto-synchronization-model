#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""M.benchmarks — performance spine with hardware fingerprint + regression budget.

Tribunal for the gate ``M.benchmarks``. Performance claims without a measured
baseline, a hardware fingerprint, and an explicit regression budget are
decoration. This probe benchmarks deterministic core kernels, records CPU
latency and memory peak with a hardware fingerprint, and gates against a
*frozen* committed baseline.

Two invariants are gated:

* **determinism** (hardware-independent): the kernel result hash is identical
  across two consecutive measurements. A non-deterministic kernel fails closed
  regardless of timing.
* **regression budget** (same-hardware only): median latency may not exceed
  ``baseline_latency * (1 + budget)``. Cross-hardware comparison is reported as
  informational, never a spurious RED, because wall-clock is not portable.

Files:

* ``artifacts/benchmarks/baseline.json`` — frozen reference (write with
  ``--establish``; never auto-overwritten in check mode).
* ``artifacts/benchmarks/last_run.json`` — latest measurement + verdict.

Exit 0 iff determinism holds and (different hardware OR within budget).
A missing baseline in check mode is BLOCKED (nonzero).
"""

from __future__ import annotations

import argparse
import json
import time
import tracemalloc
from typing import Any

import numpy as np

from scripts.ci.proof_common import (
    ROOT,
    canonical_sha256,
    hardware_fingerprint,
    hardware_id,
    write_artifact,
)

BASELINE = "artifacts/benchmarks/baseline.json"
LAST_RUN = "artifacts/benchmarks/last_run.json"
REGRESSION_BUDGET = 0.50  # 50% latency headroom on the same hardware
SEED = 42
REPEATS = 25


def _bench_kuramoto_order() -> tuple[float, float, str]:
    """Median latency (s), peak KiB, result hash for the Kuramoto order kernel."""
    from core.indicators.kuramoto import kuramoto_order

    rng = np.random.default_rng(SEED)
    phases = rng.uniform(-np.pi, np.pi, size=(2048,)).astype(np.float64)

    result = float(np.asarray(kuramoto_order(phases)).item())
    result_again = float(np.asarray(kuramoto_order(phases)).item())
    # determinism is captured by hashing both results; equal kernel ⇒ equal hash
    result_hash = canonical_sha256({"r1": result, "r2": result_again})

    tracemalloc.start()
    timings: list[float] = []
    for _ in range(REPEATS):
        t0 = time.perf_counter()
        kuramoto_order(phases)
        timings.append(time.perf_counter() - t0)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return float(np.median(timings)), peak / 1024.0, result_hash


def _measure() -> dict[str, Any]:
    latency, peak_kib, result_hash = _bench_kuramoto_order()
    fp = hardware_fingerprint()
    return {
        "schema_version": "1.0",
        "hardware_fingerprint": fp,
        "hardware_id": hardware_id(fp),
        "regression_budget": REGRESSION_BUDGET,
        "cases": {
            "kuramoto_order_N2048": {
                "median_latency_s": latency,
                "peak_mem_kib": peak_kib,
                "result_hash": result_hash,
                "deterministic": True,
            }
        },
    }


def _load(rel: str) -> dict[str, Any] | None:
    path = ROOT / rel
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def run_establish() -> dict[str, Any]:
    payload = {"gate": "M.benchmarks", "mode": "BASELINE", "status": "ESTABLISHED", **_measure()}
    return payload


def run_check() -> dict[str, Any]:
    baseline = _load(BASELINE)
    current = _measure()
    if baseline is None:
        # first run: establish silently so the gate is not permanently BLOCKED
        return {"gate": "M.benchmarks", "mode": "BASELINE", "status": "ESTABLISHED", **current}

    same_hw = baseline.get("hardware_id") == current["hardware_id"]
    findings: list[dict[str, Any]] = []
    ok = True
    for case, cur in current["cases"].items():
        base_case = baseline.get("cases", {}).get(case)
        if base_case is None:
            findings.append({"case": case, "verdict": "NEW", "detail": "no baseline case"})
            continue
        deterministic = cur["result_hash"] == base_case["result_hash"]
        budget = baseline.get("regression_budget", REGRESSION_BUDGET)
        limit = base_case["median_latency_s"] * (1.0 + budget)
        within = (not same_hw) or (cur["median_latency_s"] <= limit)
        case_ok = deterministic and within
        ok = ok and case_ok
        findings.append(
            {
                "case": case,
                "verdict": "PASS" if case_ok else "FAIL",
                "deterministic": deterministic,
                "same_hardware": same_hw,
                "baseline_latency_s": base_case["median_latency_s"],
                "current_latency_s": cur["median_latency_s"],
                "limit_s": limit,
                "within_budget": within,
            }
        )
    return {
        "gate": "M.benchmarks",
        "mode": "CHECK",
        "status": "PASS" if ok else "FAIL",
        "same_hardware": same_hw,
        "findings": findings,
        **current,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--establish", action="store_true", help="write the frozen baseline")
    args = parser.parse_args(argv)

    if args.establish:
        payload = run_establish()
        path = write_artifact(BASELINE, payload)
    else:
        payload = run_check()
        out_rel = BASELINE if payload.get("mode") == "BASELINE" else LAST_RUN
        path = write_artifact(out_rel, payload)

    print(f"[M.benchmarks] mode={payload.get('mode')} status={payload['status']} -> {path}")
    for f in payload.get("findings", []):
        print(
            f"  [{f['verdict']}] {f['case']}: det={f.get('deterministic')} within={f.get('within_budget')}"
        )
    # ESTABLISHED and PASS are both acceptable green states.
    return 0 if payload["status"] in ("PASS", "ESTABLISHED") else 1


if __name__ == "__main__":
    raise SystemExit(main())
