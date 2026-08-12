#!/usr/bin/env python3
"""RVG-1 mutation normalizer — collapse any mutation engine into one schema.

Supports explicit counts (the deterministic, CI-friendly path) or parsing a
mutmut / cosmic-ray / mutatest summary. Emits:

    {
      "tool": "...",
      "killed": int,
      "survived": int,
      "timeout": int,
      "incompetent": int,
      "valid_mutants": killed + survived,
      "mutation_score": killed / valid_mutants * 100
    }

Policy (see audit/RVG_PROTOCOL.md §6):
  * valid_mutants = killed + survived. Timeout and incompetent/equivalent
    mutants are reported but never silently folded into `killed`.
  * Timeouts count as killed ONLY with --timeout-stable (asserts the suite has a
    fixed, non-hung runtime). Even then they are also kept in the `timeout`
    field for auditability.
  * valid_mutants == 0 is written through unchanged; the verdict engine treats
    it as fail-closed (no oracle signal).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


def normalize(
    *,
    tool: str,
    killed: int,
    survived: int,
    timeout: int = 0,
    incompetent: int = 0,
    timeout_stable: bool = False,
) -> dict[str, object]:
    for name, val in (
        ("killed", killed),
        ("survived", survived),
        ("timeout", timeout),
        ("incompetent", incompetent),
    ):
        if val < 0:
            raise ValueError(f"{name} must be >= 0, got {val}")

    effective_killed = killed + (timeout if timeout_stable else 0)
    valid = effective_killed + survived
    score = round(effective_killed / valid * 100.0, 2) if valid else 0.0
    return {
        "tool": tool,
        "killed": effective_killed,
        "survived": survived,
        "timeout": timeout,
        "incompetent": incompetent,
        "timeout_counted_as_killed": bool(timeout_stable),
        "valid_mutants": valid,
        "mutation_score": score,
    }


def bootstrap_report(tool: str = "none") -> dict[str, object]:
    """Explicit, non-enforcing mutation evidence.

    Emitted when the repo cannot yet run a real mutation campaign under RVG. It
    claims NO mutation_score (a fabricated `tool: none` score would be placeholder
    evidence). The verdict engine records it as non-enforcing; the enforce-mode
    verdict assertion rejects it. See audit/RVG_PROTOCOL.md §6.
    """
    return {
        "tool": tool,
        "killed": 0,
        "survived": 0,
        "timeout": 0,
        "incompetent": 0,
        "valid_mutants": 0,
        "mutation_score": None,
        "bootstrap_report_only": True,
    }


_MUTMUT_RE = {
    "killed": re.compile(r"🎉\s*(\d+)"),
    "timeout": re.compile(r"⏰\s*(\d+)"),
    "survived": re.compile(r"🙁\s*(\d+)"),
    "incompetent": re.compile(r"🔇\s*(\d+)"),
}


def parse_mutmut(text: str) -> dict[str, int]:
    """Parse a `mutmut results`/summary line into raw counts."""
    out = {"killed": 0, "survived": 0, "timeout": 0, "incompetent": 0}
    for key, rx in _MUTMUT_RE.items():
        m = rx.search(text)
        if m:
            out[key] = int(m.group(1))
    return out


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Normalize mutation results for RVG")
    p.add_argument("--tool", default="unknown")
    p.add_argument("--killed", type=int)
    p.add_argument("--survived", type=int)
    p.add_argument("--timeout", type=int, default=0)
    p.add_argument("--incompetent", type=int, default=0)
    p.add_argument(
        "--timeout-stable",
        action="store_true",
        help="count timeout mutants as killed (assert fixed, non-hung runtime)",
    )
    p.add_argument("--from-mutmut", help="path to a captured `mutmut results` summary")
    p.add_argument(
        "--bootstrap-report-only",
        action="store_true",
        help="emit explicit non-enforcing mutation evidence (no score claimed)",
    )
    p.add_argument("--out", required=True)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.bootstrap_report_only:
        result: dict[str, object] = bootstrap_report()
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print("mutation: bootstrap_report_only (no score claimed)")
        return 0

    if args.from_mutmut:
        counts = parse_mutmut(Path(args.from_mutmut).read_text(encoding="utf-8"))
        tool = "mutmut"
    else:
        if args.killed is None or args.survived is None:
            print(
                "error: provide --killed and --survived, or --from-mutmut",
                file=sys.stderr,
            )
            return 2
        counts = {
            "killed": args.killed,
            "survived": args.survived,
            "timeout": args.timeout,
            "incompetent": args.incompetent,
        }
        tool = args.tool

    result = normalize(tool=tool, timeout_stable=args.timeout_stable, **counts)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        f"mutation: killed={result['killed']} survived={result['survived']} "
        f"score={result['mutation_score']}%"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
