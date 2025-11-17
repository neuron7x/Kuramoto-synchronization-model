"""Guardrail enforcing minimum mutation kill rates in CI."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from mutmut.__main__ import (
    SourceFileMutationData,
    ensure_config_loaded,
    status_by_exit_code,
    walk_source_files,
)

_EXCLUDED_STATUSES: set[str] = {"not checked"}
_FAILURE_STATUSES: set[str] = {
    "survived",
    "suspicious",
    "timeout",
    "no tests",
    "segfault",
    "skipped",
    "unknown",
}


@dataclass(frozen=True)
class MutationSummary:
    """Aggregated statistics for a mutmut run."""

    total: int
    counted: int
    killed: int
    status_counts: Mapping[str, int]

    @property
    def kill_rate(self) -> float:
        if self.counted == 0:
            return 0.0
        return self.killed / self.counted

    @property
    def failed(self) -> int:
        return max(self.counted - self.killed, 0)


def _collect_summary() -> MutationSummary:
    ensure_config_loaded()

    counts: Counter[str] = Counter()
    total = 0

    for path in walk_source_files():
        if not str(path).endswith(".py"):
            continue
        data = SourceFileMutationData(path=path)
        data.load()
        if not data.exit_code_by_key:
            continue
        for exit_code in data.exit_code_by_key.values():
            status = status_by_exit_code.get(exit_code, "unknown")
            counts[status] += 1
            total += 1

    counted = total - sum(counts[status] for status in _EXCLUDED_STATUSES)
    killed = counts.get("killed", 0)

    return MutationSummary(
        total=total, counted=counted, killed=killed, status_counts=counts
    )


def _render_summary(summary: MutationSummary) -> str:
    ordered_statuses = sorted(summary.status_counts.items())
    status_fragments = [f"{name}={count}" for name, count in ordered_statuses if count]
    status_section = (
        ", ".join(status_fragments) if status_fragments else "no mutants discovered"
    )
    kill_percentage = summary.kill_rate * 100.0
    return (
        "Mutation summary: "
        f"kill_rate={kill_percentage:.2f}% (killed={summary.killed}/counted={summary.counted}, total={summary.total}); "
        f"breakdown: {status_section}"
    )


def _write_summary(
    summary: MutationSummary, *, destination: Path | None, threshold: float
) -> None:
    if destination is None:
        return
    payload = {
        "total_mutants": summary.total,
        "counted_mutants": summary.counted,
        "killed_mutants": summary.killed,
        "kill_rate": summary.kill_rate,
        "threshold": threshold,
        "status_counts": dict(summary.status_counts),
    }
    destination.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _validate_threshold(value: str) -> float:
    try:
        threshold = float(value)
    except ValueError as exc:  # pragma: no cover - argparse handles messaging
        raise argparse.ArgumentTypeError("threshold must be numeric") from exc
    if not 0.0 <= threshold <= 1.0:
        raise argparse.ArgumentTypeError("threshold must be between 0.0 and 1.0")
    return threshold


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--threshold",
        type=_validate_threshold,
        default=0.8,
        help="Minimum acceptable kill rate as a decimal (default: 0.8).",
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=None,
        help="Optional path to write a JSON summary for CI artifacts.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])

    summary = _collect_summary()
    message = _render_summary(summary)
    _write_summary(summary, destination=args.summary, threshold=args.threshold)

    if summary.total == 0:
        print(
            "No mutation results were found. Did you run 'mutmut run' first?",
            file=sys.stderr,
        )
        return 2

    print(message)

    if summary.counted == 0:
        print(
            "All mutants were marked as 'not checked'; mutation suite must be executed before enforcing the gate.",
            file=sys.stderr,
        )
        return 3

    if summary.kill_rate + 1e-9 < args.threshold:
        failing_statuses = {
            name: summary.status_counts.get(name, 0)
            for name in _FAILURE_STATUSES
            if summary.status_counts.get(name, 0)
        }
        if failing_statuses:
            details = ", ".join(
                f"{name}={count}" for name, count in sorted(failing_statuses.items())
            )
            print(
                f"Mutation kill rate below threshold; unresolved mutants: {details}",
                file=sys.stderr,
            )
        else:
            print("Mutation kill rate below threshold.", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
