from __future__ import annotations

import statistics
import sys
import time
import tracemalloc
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runtime.hyperdirect_veto import HyperdirectConfig, HyperdirectVeto  # noqa: E402

__all__ = ["PerfResult", "run_benchmark", "main"]


@dataclass(frozen=True)
class PerfResult:
    evaluations: int
    channels: int
    ns_per_eval: float
    p99_ns_per_eval: float
    peak_memory_kb: float
    decisions_passed: int


def run_benchmark(evaluations: int = 200_000, channels: int = 7) -> PerfResult:
    """Deterministic latency characterisation.

    Fixed inputs (no RNG in the measured path) so the number is
    reproducible run-to-run; the only variance is host scheduling, which
    is why p99 is reported alongside the mean.
    """
    gate = HyperdirectVeto(HyperdirectConfig(conflict_gain=1.0))
    conflict = {f"c{i}": 0.1 + 0.05 * i for i in range(channels)}
    margin = 0.42

    # Warm up import/JIT-free interpreter caches.
    for _ in range(1000):
        gate.evaluate(conflict, evidence_margin=margin)

    samples: list[float] = []
    passed = 0
    tracemalloc.start()
    for _ in range(evaluations):
        t0 = time.perf_counter_ns()
        d = gate.evaluate(conflict, evidence_margin=margin)
        samples.append(float(time.perf_counter_ns() - t0))
        passed += int(d.passed)
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    samples.sort()
    p99 = samples[min(len(samples) - 1, int(0.99 * len(samples)))]
    return PerfResult(
        evaluations=evaluations,
        channels=channels,
        ns_per_eval=statistics.fmean(samples),
        p99_ns_per_eval=p99,
        peak_memory_kb=peak / 1024.0,
        decisions_passed=passed,
    )


def main() -> int:
    result = run_benchmark()
    print("HyperdirectVeto — performance characterisation (provenance)")
    print(f"  evaluations      : {result.evaluations}")
    print(f"  channels/eval    : {result.channels}")
    print(f"  mean ns/eval     : {result.ns_per_eval:,.1f}")
    print(f"  p99  ns/eval     : {result.p99_ns_per_eval:,.1f}")
    print(f"  peak memory (KB) : {result.peak_memory_kb:,.2f}")
    print(f"  decisions passed : {result.decisions_passed}/{result.evaluations}")
    print(
        "  note            : pure deterministic path; no clock/RNG/IO "
        "in evaluate(); number is host-relative, not a portable claim."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
