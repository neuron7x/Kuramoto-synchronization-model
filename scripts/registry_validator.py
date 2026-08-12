"""Registry validator — enforces fail-closed policy on research lines.

Reads config/research_line_registry.yaml and exposes check functions that
future automation (pre-commit, CI, pipeline orchestrators) can call
before attempting to start a run.

Policy:
  - A line with status != OPEN is *terminally closed*. No parameter
    rescue, no same-family same-substrate retest.
  - To continue on a closed substrate, the caller must supply either:
      (a) a new line_id whose allowed_next_action matches one of the
          registry-allowed next-actions, OR
      (b) a signal_family / substrate pair that is not already flagged
          as rejected.
  - A revival attempt on an already-rejected (family, substrate) pair
    raises LineClosedError.

This is intentionally a tiny, self-contained module — no framework,
no indirection. The tests exercise the policy directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


class LineClosedError(Exception):
    """Raised when an attempt is made to revive a REJECTED research line."""


@dataclass(frozen=True)
class RegistryLine:
    line_id: str
    signal_family: str
    substrate: str
    status: str
    verdict: str | None
    wave2_authorized: bool
    parameter_rescue_allowed: bool
    same_family_same_substrate_retest_allowed: bool
    allowed_next_action: str
    evidence_path: str | None
    lock_sha: str | None
    complete_sha: str | None


def load_registry(path: str | Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if data is None or "lines" not in data:
        raise ValueError(f"registry at {path} is empty or malformed (no 'lines' key)")
    return data


def get_line(registry: dict[str, Any], line_id: str) -> RegistryLine:
    lines = registry.get("lines", {})
    if line_id not in lines:
        raise KeyError(f"line_id {line_id!r} not in registry")
    entry = lines[line_id]
    return RegistryLine(
        line_id=line_id,
        signal_family=entry["signal_family"],
        substrate=entry["substrate"],
        status=entry["status"],
        verdict=entry.get("verdict"),
        wave2_authorized=bool(entry["wave2_authorized"]),
        parameter_rescue_allowed=bool(entry["parameter_rescue_allowed"]),
        same_family_same_substrate_retest_allowed=bool(
            entry["same_family_same_substrate_retest_allowed"]
        ),
        allowed_next_action=entry["allowed_next_action"],
        evidence_path=entry.get("evidence_path"),
        lock_sha=entry.get("lock_sha"),
        complete_sha=entry.get("complete_sha"),
    )


def is_line_closed(registry: dict[str, Any], line_id: str) -> bool:
    line = get_line(registry, line_id)
    return line.status != "OPEN"


def check_family_substrate_allowed(
    registry: dict[str, Any], signal_family: str, substrate: str
) -> None:
    """Raise LineClosedError if any rejected line already covers this pair.

    This is the primary gate future orchestrators must call before
    starting a new experiment. If a REJECTED line exists for exactly
    (signal_family, substrate), the caller is attempting a forbidden
    resurrection and must be blocked.
    """
    for line_id, entry in registry.get("lines", {}).items():
        if (
            entry["signal_family"] == signal_family
            and entry["substrate"] == substrate
            and entry["status"] == "REJECTED"
        ):
            raise LineClosedError(
                f"cannot start experiment on (family={signal_family!r}, "
                f"substrate={substrate!r}): line {line_id!r} is REJECTED "
                f"with verdict={entry.get('verdict')!r}; "
                f"allowed_next_action={entry['allowed_next_action']!r}. "
                f"See {entry.get('evidence_path')} and "
                f"{entry.get('canonical_fail_note', '<no fail note>')} for evidence."
            )


def allowed_next_actions(registry: dict[str, Any]) -> list[str]:
    return list(registry.get("allowed_next_actions", []))


def assert_rejected_line_invariants(line: RegistryLine) -> None:
    """Every REJECTED line must have the fail-closed flags set coherently."""
    if line.status != "REJECTED":
        return
    errors: list[str] = []
    if line.wave2_authorized:
        errors.append("wave2_authorized must be false when status == REJECTED")
    if line.parameter_rescue_allowed:
        errors.append("parameter_rescue_allowed must be false when status == REJECTED")
    if line.same_family_same_substrate_retest_allowed:
        errors.append(
            "same_family_same_substrate_retest_allowed must be false when status == REJECTED"
        )
    if line.allowed_next_action == "continue_same_line":
        errors.append("allowed_next_action must not be 'continue_same_line' when REJECTED")
    if errors:
        raise AssertionError(
            f"REJECTED line {line.line_id!r} has incoherent policy flags: " + "; ".join(errors)
        )


# ------------------------------------------------------------------ #
# CLI entry-point — usable in CI as a gate
# ------------------------------------------------------------------ #


def main(argv: list[str] | None = None) -> int:
    import argparse

    p = argparse.ArgumentParser(description="Research-line registry validator")
    p.add_argument(
        "--registry",
        default="config/research_line_registry.yaml",
        help="path to registry YAML",
    )
    p.add_argument(
        "--check-pair",
        nargs=2,
        metavar=("SIGNAL_FAMILY", "SUBSTRATE"),
        help="fail if this (family, substrate) pair is already REJECTED",
    )
    args = p.parse_args(argv)

    registry = load_registry(args.registry)
    # Always validate all REJECTED lines for invariant coherence.
    for line_id in registry.get("lines", {}):
        line = get_line(registry, line_id)
        assert_rejected_line_invariants(line)

    if args.check_pair:
        family, substrate = args.check_pair
        try:
            check_family_substrate_allowed(registry, family, substrate)
        except LineClosedError as exc:
            print(f"BLOCKED: {exc}")
            return 2

    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
