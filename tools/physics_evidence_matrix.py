#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Physics evidence matrix generator (Task 7).

Reads `.claude/physics/INVARIANTS.yaml` and emits a deterministic
markdown table mapping each registered invariant to its evidence
surface: tier, priority, source path, unit-test path,
integration-test path (if declared), runtime status, related
invariants. Output is governance, not vibes.

Determinism:
  - Invariants emitted in registry-iteration order (preserved by
    validate_tests.load_invariants).
  - No clock access. No RNG. No external data.
  - Re-running produces byte-identical output for unchanged YAML.

Usage:
    python tools/physics_evidence_matrix.py
    python tools/physics_evidence_matrix.py --out docs/physics/evidence_matrix.md

Exit codes:
    0 — matrix generated
    1 — registry empty / unreadable
    4 — invocation error
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / ".claude" / "physics"))

from validate_tests import load_invariants  # noqa: E402


def _yes_no(value: str) -> str:
    if value.lower() in {"yes", "true"}:
        return "yes"
    if value.lower() in {"no", "false"}:
        return "no"
    return "—"


def _path_exists(rel: str) -> bool:
    if not rel:
        return False
    return (REPO_ROOT / rel.split("::", 1)[0]).exists()


def render_matrix(invariants: dict[str, dict[str, str]]) -> str:
    """Render markdown table from invariant registry. Deterministic."""
    lines: list[str] = []
    lines.append("# Physics Invariant Evidence Matrix")
    lines.append("")
    lines.append(
        "Generated deterministically from `.claude/physics/INVARIANTS.yaml` by "
        "`tools/physics_evidence_matrix.py`. Do not edit by hand — re-run the "
        "generator after registry changes."
    )
    lines.append("")
    lines.append(
        "| INV ID | Tier | Priority | Source | Unit Test | "
        "Integration Test | Falsifier Node | Runtime | Source ✓ | Unit ✓ | Integ ✓ |"
    )
    lines.append("|---|---|---|---|---|---|---|---|:---:|:---:|:---:|")
    for inv_id, data in invariants.items():
        tier = data.get("provenance", "—") or "—"
        priority = data.get("priority", "—") or "—"
        source = data.get("source", "—") or "—"
        unit_test = data.get("tests", "—") or "—"
        integration = data.get("integration_test", "—") or "—"
        falsifier = data.get("falsifier_test", "—") or "—"
        runtime = _yes_no(data.get("runtime_evaluable", ""))
        source_ok = "✓" if _path_exists(source) else ("—" if source == "—" else "✗")
        unit_ok = "✓" if _path_exists(unit_test) else ("—" if unit_test == "—" else "✗")
        integ_ok = "✓" if _path_exists(integration) else ("—" if integration == "—" else "✗")
        lines.append(
            f"| {inv_id} | {tier} | {priority} | `{source}` | `{unit_test}` | "
            f"`{integration}` | `{falsifier}` | {runtime} | "
            f"{source_ok} | {unit_ok} | {integ_ok} |"
        )
    lines.append("")
    lines.append(f"Total invariants registered: {len(invariants)}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output path (default: stdout).",
    )
    args = parser.parse_args(argv)
    invariants = load_invariants()
    if not invariants:
        print("ERROR: no invariants loaded", file=sys.stderr)
        return 1
    text = render_matrix(invariants)
    if args.out is None:
        print(text)
    else:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
        print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
