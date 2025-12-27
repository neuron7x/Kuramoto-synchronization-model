#!/usr/bin/env python
"""Compare thermodynamic state snapshots."""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List

ABS_TOL = 1e-6
REL_TOL = 0.05  # 5% relative tolerance


@dataclass(frozen=True)
class DiffResult:
    key: str
    baseline: Any
    candidate: Any
    delta: float | None
    within_tolerance: bool


def _load_state(path: Path) -> Dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit(f"{path} must contain a JSON object")
    return payload


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(value)


def compare_states(
    baseline: Dict[str, Any],
    candidate: Dict[str, Any],
    *,
    abs_tol: float = ABS_TOL,
    rel_tol: float = REL_TOL,
) -> List[DiffResult]:
    results: List[DiffResult] = []
    keys = set(baseline) | set(candidate)
    for key in sorted(keys):
        base = baseline.get(key)
        cand = candidate.get(key)
        if _is_number(base) and _is_number(cand):
            delta = float(cand) - float(base)
            rel = abs(delta) / (abs(float(base)) + ABS_TOL)
            within = abs(delta) <= abs_tol or rel <= rel_tol
        else:
            delta = None
            within = base == cand
        results.append(DiffResult(key, base, cand, delta, within))
    return results


def _format_result(result: DiffResult) -> str:
    status = "OK" if result.within_tolerance else "DRIFT"
    if result.delta is None:
        return f"[{status}] {result.key}: {result.baseline!r} -> {result.candidate!r}"
    return (
        f"[{status}] {result.key}: {result.baseline} -> {result.candidate} "
        f"(delta={result.delta:+.6f})"
    )


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare thermodynamic state snapshots")
    parser.add_argument("baseline", type=Path, help="Path to baseline JSON state")
    parser.add_argument("candidate", type=Path, help="Path to candidate JSON state")
    parser.add_argument(
        "--abs-tol",
        type=float,
        default=ABS_TOL,
        help=f"Absolute tolerance for numeric fields (default: {ABS_TOL})",
    )
    parser.add_argument(
        "--rel-tol",
        type=float,
        default=REL_TOL,
        help=f"Relative tolerance for numeric fields (default: {REL_TOL})",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    baseline = _load_state(args.baseline)
    candidate = _load_state(args.candidate)

    results = compare_states(baseline, candidate, abs_tol=args.abs_tol, rel_tol=args.rel_tol)
    drift = [result for result in results if not result.within_tolerance]

    for result in results:
        print(_format_result(result))

    if drift:
        print(f"{len(drift)} field(s) exceeded tolerance.")
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(main())
