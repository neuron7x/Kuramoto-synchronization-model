# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""WP-03 — Physics Release Scorecard as a fail-closed GATE.

Research question: can partial physics evidence silently become release-ready?

This gate makes that impossible by construction. It RECOMPUTES readiness from the
per-dimension states and fails closed when:

  * ``claimed_ready`` is true while any REQUIRED dimension is below
    ``min_state_for_ready`` (PARTIAL marked as READY — the core lie), or
  * a dimension claims a verified state (>= LOCAL_VERIFIED) with empty
    ``evidence`` (a claim with no proof), or
  * an unknown state / malformed scorecard is presented.

The detection core (:func:`evaluate`) is pure and offline-testable.

Run::

    python tools/release/check_physics_release_scorecard.py
    python tools/release/check_physics_release_scorecard.py --json
    python tools/release/check_physics_release_scorecard.py --path physics_release_scorecard.yml

Exit code 0 iff the scorecard is internally honest; non-zero otherwise.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCORECARD = REPO_ROOT / "physics_release_scorecard.yml"

# Strict low-to-high ordering. Index == rank.
STATES: tuple[str, ...] = (
    "FALSE",
    "UNTESTED",
    "PARTIAL",
    "LOCAL_VERIFIED",
    "CI_VERIFIED",
    "EVIDENCE_BEARING",
)
_RANK = {s: i for i, s in enumerate(STATES)}
# States at or above this rank assert verification and therefore require evidence.
_EVIDENCE_FROM = _RANK["LOCAL_VERIFIED"]


@dataclass(frozen=True)
class Result:
    computed_ready: bool
    claimed_ready: bool
    min_state_for_ready: str
    blocking_dimensions: list[str]
    hard_violations: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.hard_violations


def evaluate(scorecard: dict[str, Any]) -> Result:
    """Recompute readiness from dimension states and detect dishonesty."""
    hard: list[str] = []

    min_ready = str(scorecard.get("min_state_for_ready", "CI_VERIFIED"))
    if min_ready not in _RANK:
        hard.append(f"unknown min_state_for_ready: {min_ready!r}")
        min_ready_rank = _RANK["CI_VERIFIED"]
    else:
        min_ready_rank = _RANK[min_ready]

    claimed_ready = bool(scorecard.get("claimed_ready", False))
    dims = scorecard.get("dimensions", [])
    if not isinstance(dims, list) or not dims:
        hard.append("scorecard has no dimensions")
        dims = []

    blocking: list[str] = []
    required_seen = False
    for dim in dims:
        if not isinstance(dim, dict):
            hard.append(f"dimension is not a mapping: {dim!r}")
            continue
        name = str(dim.get("name", "<unnamed>"))
        # .upper() guards the YAML 1.1 footgun where a bare FALSE parses to a bool.
        state = str(dim.get("state", "")).upper()
        if state not in _RANK:
            hard.append(f"{name}: unknown state {state!r}")
            continue
        required = bool(dim.get("required", False))
        evidence = str(dim.get("evidence", "") or "").strip()
        if _RANK[state] >= _EVIDENCE_FROM and not evidence:
            hard.append(f"{name}: state {state} claims verification but evidence is empty")
        if required:
            required_seen = True
            if _RANK[state] < min_ready_rank:
                blocking.append(f"{name}({state})")

    if not required_seen and dims:
        hard.append("no required dimensions — a release gate with nothing required is decorative")

    computed_ready = not blocking and not any(v for v in hard)
    # The core anti-lie: you may not claim READY while a required dimension is below the bar.
    if claimed_ready and blocking:
        hard.append(
            "claimed_ready=true but required dimensions below "
            f"{min_ready}: {', '.join(blocking)} (PARTIAL != READY)"
        )

    return Result(
        computed_ready=computed_ready,
        claimed_ready=claimed_ready,
        min_state_for_ready=min_ready,
        blocking_dimensions=blocking,
        hard_violations=hard,
    )


def _load(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        data: Any = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: scorecard must be a mapping")
    return data


def _print_human(result: Result) -> None:
    print("=" * 64)
    print("Physics Release Scorecard Gate")
    print("=" * 64)
    print(f"min_state_for_ready: {result.min_state_for_ready}")
    print(f"claimed_ready:       {result.claimed_ready}")
    print(f"computed_ready:      {result.computed_ready}")
    if result.blocking_dimensions:
        print(f"\nBlocking required dimensions ({len(result.blocking_dimensions)}):")
        for d in result.blocking_dimensions:
            print(f"  - {d}")
    if result.hard_violations:
        print(f"\nHARD violations ({len(result.hard_violations)}):")
        for v in result.hard_violations:
            print(f"  [X] {v}")
        print("\nFAIL")
    else:
        verdict = "RELEASE-READY" if result.computed_ready else "NOT release-ready (honest)"
        print(f"\nScorecard is internally honest — {verdict}.")
        print("PASS")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", default=str(DEFAULT_SCORECARD), help="scorecard YAML path")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args(argv)

    result = evaluate(_load(Path(args.path)))
    if args.json:
        print(
            json.dumps(
                {
                    "computed_ready": result.computed_ready,
                    "claimed_ready": result.claimed_ready,
                    "min_state_for_ready": result.min_state_for_ready,
                    "blocking_dimensions": result.blocking_dimensions,
                    "hard_violations": result.hard_violations,
                    "passed": result.passed,
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        _print_human(result)
    return 0 if result.passed else 1


if __name__ == "__main__":
    sys.exit(main())
