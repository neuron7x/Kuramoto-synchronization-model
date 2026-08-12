# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Run static application security tests (SAST) using Bandit."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Sequence

_SEVERITY_ORDER = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--paths",
        nargs="+",
        default=["core", "execution", "backtest", "application"],
        help="Project directories scanned by Bandit.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Optional Bandit configuration file.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports/security/bandit.json"),
        help="Destination for the Bandit JSON report.",
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=Path("reports/security/sast_summary.json"),
        help="Path for a condensed JSON summary of findings.",
    )
    parser.add_argument(
        "--fail-on-severity",
        choices=sorted(_SEVERITY_ORDER),
        default="MEDIUM",
        help="Minimum severity that fails the run (default: MEDIUM).",
    )
    return parser.parse_args(argv)


def _ensure_directory(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _run_bandit(paths: Sequence[str], *, config: Path | None, destination: Path) -> Path:
    with tempfile.NamedTemporaryFile("w+", suffix=".json", delete=False) as handle:
        temp_path = Path(handle.name)
    command: list[str] = [
        sys.executable,
        "-m",
        "bandit",
        "-r",
        *paths,
        "-f",
        "json",
        "-o",
        str(temp_path),
    ]
    if config is not None:
        command.extend(["-c", str(config)])
    env = os.environ.copy()
    env.setdefault("PYTHONPATH", str(Path.cwd()))
    completed = subprocess.run(command, env=env, check=False)
    if completed.returncode not in (0, 1):
        raise RuntimeError(
            f"Bandit execution failed ({completed.returncode}): {shlex.join(command)}"
        )
    if not temp_path.exists() or temp_path.stat().st_size == 0:
        raise RuntimeError(
            "Bandit did not produce a report; ensure the tool is installed and available."
        )
    destination.write_text(temp_path.read_text(encoding="utf-8"), encoding="utf-8")
    temp_path.unlink(missing_ok=True)
    return destination


def _collect_summary(report_path: Path) -> dict:
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    results = payload.get("results", [])
    counts: dict[str, int] = {severity: 0 for severity in _SEVERITY_ORDER}
    for finding in results:
        severity = str(finding.get("issue_severity", "")).upper()
        if severity in counts:
            counts[severity] += 1
    highest: str | None = None
    for severity in _SEVERITY_ORDER:
        if counts[severity]:
            highest = severity
    summary = {
        "total_findings": len(results),
        "severity_breakdown": counts,
        "highest_severity": highest or "NONE",
    }
    metrics = payload.get("metrics", {})
    if metrics:
        summary["metrics"] = metrics
    return summary


def _severity_fails(highest: str, threshold: str) -> bool:
    if highest == "NONE":
        return False
    return _SEVERITY_ORDER.get(highest, 0) >= _SEVERITY_ORDER.get(threshold, 0)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])

    _ensure_directory(args.output)
    _ensure_directory(args.summary)

    report_path = _run_bandit(args.paths, config=args.config, destination=args.output)
    summary = _collect_summary(report_path)
    summary_path = args.summary
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    highest = summary["highest_severity"]
    print("Bandit summary:", json.dumps(summary, indent=2, sort_keys=True))

    if summary["total_findings"] == 0:
        return 0

    if _severity_fails(highest, args.fail_on_severity):
        print(
            (
                f"Security scan failed: highest severity {highest} meets or exceeds threshold {args.fail_on_severity}."
            ),
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
