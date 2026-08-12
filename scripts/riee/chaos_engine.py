from __future__ import annotations

from pathlib import Path

from runtime.riee.engine import enforce_runtime_invariant


def run_chaos(iterations: int = 10000) -> tuple[int, int]:
    detected = 0
    for i in range(iterations):
        gamma = 1.0 + (1e-3 if i % 2 == 0 else 0.0)
        status = enforce_runtime_invariant(gamma, Path("CLAIMS.md"))
        if not status.state_validity:
            detected += 1
    return detected, iterations


if __name__ == "__main__":
    d, n = run_chaos()
    print(f"detected={d} total={n}")
    raise SystemExit(0 if d == n // 2 else 1)
