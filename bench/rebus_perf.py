from __future__ import annotations

import sys
import time
import tracemalloc
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@dataclass
class PerfResult:
    steps: int
    avg_ms_per_step: float
    peak_memory_mb: float
    deepcopy_calls: int


def _apply_ok(_: Mapping[str, float]) -> bool:
    return True


def run_benchmark(steps: int = 10_000) -> PerfResult:
    import runtime.rebus_gate as pag
    from runtime.rebus_gate import RebusGate

    gate = RebusGate()
    priors = {"p1": 1.0, "p2": 0.7, "p3": 1.3}

    deepcopy_counter = {"count": 0}
    original_deepcopy: Callable[..., object] = pag.deepcopy

    def _counting_deepcopy(obj: object) -> object:
        deepcopy_counter["count"] += 1
        return original_deepcopy(obj)

    pag.deepcopy = _counting_deepcopy  # type: ignore[assignment]
    tracemalloc.start()
    t0 = time.perf_counter()
    try:
        for i in range(steps):
            gate.activate(
                f"cycle-{i}",
                priors,
                parent_nominal=True,
                current_coherence=0.95,
                apply_attenuated_priors=_apply_ok,
                apply_restored_priors=_apply_ok,
            )
            gate.step(0.1, 0.95)
            gate.step(0.1, 0.95)
            gate.step(0.1, 0.95)
            gate.reintegrate(0.95)
    finally:
        elapsed = time.perf_counter() - t0
        _current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        pag.deepcopy = original_deepcopy  # type: ignore[assignment]

    total_steps = steps * 5
    return PerfResult(
        steps=total_steps,
        avg_ms_per_step=(elapsed / total_steps) * 1000.0,
        peak_memory_mb=peak / (1024 * 1024),
        deepcopy_calls=deepcopy_counter["count"],
    )


if __name__ == "__main__":
    result = run_benchmark()
    print(f"steps={result.steps}")
    print(f"avg_ms_per_step={result.avg_ms_per_step:.6f}")
    print(f"peak_memory_mb={result.peak_memory_mb:.6f}")
    print(f"deepcopy_calls={result.deepcopy_calls}")
