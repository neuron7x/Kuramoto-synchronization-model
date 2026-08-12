#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Feature-debt lock — fail-closed on new features that ignore the coverage deficit.

This gate applies the system's Fail-Closed philosophy to the GENERATION PROCESS
itself: while a critical surface (``backtest/``, ``analytics/``) carries a
coverage deficit, a pull request that adds NEW production feature code is BLOCKED
unless it also pays the debt down — i.e. it adds test coverage for a deficit
surface — or it declares an explicit, audited exemption.

Decision (pure function of the diff, no coverage run needed):

    feature_lines  = net added production lines under any tracked surface path
    debt_paydown   = net added test lines targeting a deficit surface
    exempt         = a 'Debt-Exempt: <reason>' trailer in any commit in the range

    BLOCK iff  feature_lines > FEATURE_THRESHOLD  AND  debt_paydown == 0  AND  not exempt

The exemption is fail-closed-with-explicit-override: legitimate non-feature work
(docs, CI, refactors) passes only by declaring the reason, which stays in history.

    python scripts/ci/check_feature_debt_lock.py --base-ref origin/main
    python scripts/ci/check_feature_debt_lock.py --base-ref origin/main --json out.json
"""

from __future__ import annotations

import argparse
import json
import subprocess as process
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TARGETS = ROOT / "configs" / "quality" / "coverage_targets.toml"

DEFICIT_SURFACES: tuple[str, ...] = ("backtest", "analytics")
FEATURE_THRESHOLD: int = 25
NON_FEATURE_PREFIXES: tuple[str, ...] = (
    "tests/",
    "docs/",
    ".github/",
    ".claude/",
    "scripts/",
    "tools/",
    "configs/",
    "evidence/",
    "reports/",
)
EXEMPT_TRAILER: str = "Debt-Exempt:"


def _run(args: list[str]) -> str:
    return process.run(args, check=True, capture_output=True, text=True, cwd=ROOT).stdout


def _surface_paths() -> dict[str, list[str]]:
    data = tomllib.loads(TARGETS.read_text(encoding="utf-8"))
    return {name: list(s.get("paths", [])) for name, s in data.get("surfaces", {}).items()}


def _is_production_python(path: str) -> bool:
    if not path.endswith(".py"):
        return False
    return not any(path.startswith(prefix) for prefix in NON_FEATURE_PREFIXES)


def _path_segments(path: str) -> set[str]:
    return {segment for segment in path.split("/") if segment}


def _targets_deficit_surface(path: str, deficit_paths: list[str]) -> bool:
    """True iff a test file path is structurally associated with a deficit surface."""
    if not (path.startswith("tests/") and path.endswith(".py")):
        return False

    segments = _path_segments(path)
    if any(surface in segments for surface in DEFICIT_SURFACES):
        return True

    test_path = path.removeprefix("tests/")
    return any(
        test_path == deficit.rstrip("/") or test_path.startswith(f"{deficit.rstrip('/')}/")
        for deficit in deficit_paths
    )


def _exempt_reasons(log: str) -> list[str]:
    """Return non-empty audited Debt-Exempt trailers from commit messages only."""
    reasons: list[str] = []
    for line in log.splitlines():
        stripped = line.strip()
        if not stripped.startswith(EXEMPT_TRAILER):
            continue
        reason = stripped.removeprefix(EXEMPT_TRAILER).strip()
        if reason:
            reasons.append(reason)
    return reasons


def decide(
    numstat: str,
    log: str,
    all_surface_paths: list[str],
    deficit_paths: list[str],
) -> dict[str, object]:
    """Pure decision from a git ``--numstat`` diff and a commit-log body."""
    feature_added = 0
    paydown_added = 0
    feature_files: list[str] = []
    paydown_files: list[str] = []
    for line in numstat.splitlines():
        parts = line.split("\t")
        if len(parts) != 3 or parts[0] == "-":
            continue
        added = int(parts[0])
        path = parts[2]
        if _is_production_python(path) and any(
            path.startswith(s.rstrip("/")) for s in all_surface_paths
        ):
            feature_added += added
            feature_files.append(path)
        if _targets_deficit_surface(path, deficit_paths):
            paydown_added += added
            paydown_files.append(path)

    exempt_reasons = _exempt_reasons(log)
    exempt = bool(exempt_reasons)

    blocked = feature_added > FEATURE_THRESHOLD and paydown_added == 0 and not exempt
    return {
        "deficit_surfaces": list(DEFICIT_SURFACES),
        "feature_lines_added": feature_added,
        "feature_files": sorted(feature_files),
        "debt_paydown_lines": paydown_added,
        "debt_paydown_files": sorted(paydown_files),
        "feature_threshold": FEATURE_THRESHOLD,
        "exempt": exempt,
        "exempt_reasons": exempt_reasons,
        "verdict": "BLOCK" if blocked else "PASS",
    }


def evaluate(base_ref: str) -> dict[str, object]:
    """Return the gate verdict over the real diff against ``base_ref``."""
    surface_paths = _surface_paths()
    all_surface_paths = [p for paths in surface_paths.values() for p in paths]
    deficit_paths = [p for name in DEFICIT_SURFACES for p in surface_paths.get(name, [])]
    numstat = _run(["git", "diff", "--numstat", f"{base_ref}...HEAD"])
    log = _run(["git", "log", "--format=%B", f"{base_ref}..HEAD"])
    return decide(numstat, log, all_surface_paths, deficit_paths)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-ref", default="origin/main")
    parser.add_argument("--json", dest="json_out", default=None)
    args = parser.parse_args(argv)

    # This is a changeset gate: it diffs base_ref...HEAD. If base_ref does not
    # resolve (e.g. a stale/absent `origin` remote in a local checkout — the
    # canonical remote is `grp`), fail *clean* with guidance instead of leaking
    # a raw CalledProcessError traceback. In CI `origin/main` resolves normally.
    try:
        # `base_ref...HEAD` needs a MERGE-BASE, not just a resolvable ref. A
        # stale `origin` (unrelated re-rooted history) resolves but shares no
        # ancestor, so the diff dies with exit 128. Guard the merge-base.
        process.run(
            ["git", "merge-base", args.base_ref, "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
    except process.CalledProcessError:
        print(
            f"base-ref '{args.base_ref}' shares no merge-base with HEAD in this "
            "checkout (stale/unrelated remote?); pass --base-ref <canonical ref> "
            "(e.g. grp/main). This gate compares base-ref...HEAD and needs one.",
            file=sys.stderr,
        )
        return 2

    verdict = evaluate(args.base_ref)
    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(verdict, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    if verdict["verdict"] == "BLOCK":
        print(
            "FEATURE-DEBT LOCK: BLOCKED — this PR adds "
            f"{verdict['feature_lines_added']} production lines "
            f"(> {FEATURE_THRESHOLD}) but pays down 0 test lines for the deficit "
            f"surfaces {list(DEFICIT_SURFACES)}.",
            file=sys.stderr,
        )
        print(
            "  Resolve by EITHER adding tests for backtest/ or analytics/, OR "
            "declaring 'Debt-Exempt: <reason>' in a commit message.",
            file=sys.stderr,
        )
        feature_files = verdict["feature_files"]
        if isinstance(feature_files, list):
            for feature_path in feature_files:
                print(f"    feature: {feature_path}", file=sys.stderr)
        return 1

    detail = "exempt" if verdict["exempt"] else f"paydown={verdict['debt_paydown_lines']} lines"
    print(f"FEATURE-DEBT LOCK: PASS " f"(feature_lines={verdict['feature_lines_added']}, {detail})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
