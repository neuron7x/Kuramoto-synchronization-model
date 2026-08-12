#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from geosync.core.neuro.dopamine.telemetry import bounded_value, bounded_value_delta

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts/dopamine_performance/PERFORMANCE_REPORT.json"
ITERATIONS = 2_000
BUDGET_MS = 0.5


def measure_loop(iterations: int = ITERATIONS) -> float:
    previous = 0.0
    started = time.perf_counter()
    for index in range(iterations):
        current = bounded_value(
            (index % 17) / 16.0,
            (index % 13) / 12.0,
            (index % 11) / 10.0,
            (index % 7) / 6.0,
        )
        bounded_value_delta(previous, current)
        previous = current
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    return elapsed_ms / iterations


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    step_ms = measure_loop()
    status = "PASS" if 0.0 < step_ms <= BUDGET_MS else "FAIL"
    payload = {
        "budget_ms": BUDGET_MS,
        "component": "geosync.dopamine",
        "iteration_count": ITERATIONS,
        "status": status,
        "step_ms": step_ms,
    }
    raw = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
    OUT.write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    OUT.with_suffix(OUT.suffix + ".sha256").write_text(
        f"{digest}  {OUT.name}\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {"sha256": digest, "status": status, "step_ms": step_ms},
            sort_keys=True,
        )
    )
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
