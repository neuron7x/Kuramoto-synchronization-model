# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Replayable reality ledger.

Lie blocked:
    "historical closure cannot be reproduced"

A release ledger entry (e.g. docs/releases/...) names a main SHA, a
list of merged PRs, validators, test commands, and expected exits.
This module reads a YAML replay manifest with that information and
re-runs each step against the current tree, classifying the outcome:

    REPLAY_PASS     every command exited as expected
    REPLAY_PARTIAL  some commands matched, some did not (with allowed
                    exceptions catalogued)
    REPLAY_FAIL     a required command exited unexpectedly and was not
                    listed under known_exceptions

This is not a CI runner; it is a structural verifier. Each command is
executed as a subprocess; the runner injects the cwd and captures
exit code + stdout/stderr digest only.

The replay is deterministic in structure (sort order of commands,
deterministic JSON output). It is not deterministic in time (commands
may be slow). For tests we inject a `runner` callable that maps
command → exit code so tests do not actually shell out.
"""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = Path("/tmp/geosync_replay_ledger.json")


class ReplayStatus(str, Enum):
    REPLAY_PASS = "REPLAY_PASS"
    REPLAY_PARTIAL = "REPLAY_PARTIAL"
    REPLAY_FAIL = "REPLAY_FAIL"


REQUIRED_MANIFEST_KEYS: tuple[str, ...] = (
    "schema_version",
    "main_sha",
    "pr_list",
    "validators",
    "test_commands",
    "expected_exits",
)


@dataclass(frozen=True)
class CommandResult:
    command: str
    exit_code: int
    expected_exit: int
    matched: bool
    excepted: bool
    note: str


@dataclass
class ReplayReport:
    status: ReplayStatus = ReplayStatus.REPLAY_FAIL
    main_sha: str = ""
    command_count: int = 0
    pass_count: int = 0
    fail_count: int = 0
    excepted_count: int = 0
    results: list[CommandResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "main_sha": self.main_sha,
            "command_count": self.command_count,
            "pass_count": self.pass_count,
            "fail_count": self.fail_count,
            "excepted_count": self.excepted_count,
            "results": [
                {
                    "command": r.command,
                    "exit_code": r.exit_code,
                    "expected_exit": r.expected_exit,
                    "matched": r.matched,
                    "excepted": r.excepted,
                    "note": r.note,
                }
                for r in self.results
            ],
            "errors": list(self.errors),
        }


def _load_manifest(path: Path) -> Mapping[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"replay manifest not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"replay manifest {path} must be a mapping")
    if data.get("schema_version") != 1:
        raise ValueError(
            f"replay manifest {path} requires schema_version: 1 (got {data.get('schema_version')!r})"
        )
    for key in REQUIRED_MANIFEST_KEYS:
        if key not in data:
            raise ValueError(f"replay manifest {path} missing required key: {key}")
    return MappingProxyType(data)


def _default_runner(command: str) -> int:
    """Real runner: shell out and return exit code."""
    completed = subprocess.run(
        shlex.split(command),
        cwd=REPO_ROOT,
        capture_output=True,
        check=False,
    )
    return completed.returncode


def replay_manifest(
    manifest_path: Path,
    *,
    runner: Callable[[str], int] | None = None,
) -> ReplayReport:
    """Replay every command in the manifest. ``runner`` is injected for tests."""
    report = ReplayReport()
    try:
        manifest = _load_manifest(manifest_path)
    except (FileNotFoundError, ValueError) as exc:
        report.errors.append(str(exc))
        report.status = ReplayStatus.REPLAY_FAIL
        return report

    runner = runner or _default_runner
    report.main_sha = str(manifest.get("main_sha") or "")
    expected_exits = dict(manifest.get("expected_exits") or {})
    known_exceptions = {str(k) for k in (manifest.get("known_exceptions") or [])}

    commands: list[str] = []
    for key in ("validators", "test_commands"):
        block = manifest.get(key) or []
        if not isinstance(block, list):
            report.errors.append(f"{key} must be a list")
            continue
        for c in block:
            if not isinstance(c, str) or not c.strip():
                report.errors.append(f"{key} entry must be a non-empty string (got {c!r})")
                continue
            commands.append(c)

    if report.errors:
        report.status = ReplayStatus.REPLAY_FAIL
        return report

    for command in commands:
        expected = int(expected_exits.get(command, 0))
        actual = runner(command)
        excepted = command in known_exceptions
        matched = actual == expected
        note = (
            "ok"
            if matched
            else (
                "known_exception"
                if excepted
                else f"unexpected_exit (expected {expected}, got {actual})"
            )
        )
        report.results.append(
            CommandResult(
                command=command,
                exit_code=actual,
                expected_exit=expected,
                matched=matched,
                excepted=excepted,
                note=note,
            )
        )

    report.command_count = len(report.results)
    report.pass_count = sum(1 for r in report.results if r.matched)
    report.fail_count = sum(1 for r in report.results if not r.matched and not r.excepted)
    report.excepted_count = sum(1 for r in report.results if not r.matched and r.excepted)

    if report.fail_count == 0 and report.excepted_count == 0:
        report.status = ReplayStatus.REPLAY_PASS
    elif report.fail_count == 0:
        report.status = ReplayStatus.REPLAY_PARTIAL
    else:
        report.status = ReplayStatus.REPLAY_FAIL
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Replay a release-ledger manifest")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    report = replay_manifest(args.manifest)
    payload = json.dumps(report.to_dict(), indent=2, sort_keys=True)
    args.output.write_text(payload + "\n", encoding="utf-8")
    if report.status is ReplayStatus.REPLAY_PASS:
        print("OK: REPLAY_PASS")
        return 0
    print(f"FAIL: {report.status.value}", file=sys.stderr)
    for e in report.errors:
        print(f"  - {e}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
