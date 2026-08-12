#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Calibration sensitivity-drift gate.

GeoSync doctrine: a threshold, tolerance, or sensitivity band is a *controlled
decision*, never a hand-tuned free parameter. A calibration value that moves
without an acceptor, that cannot point at the sweep which selected it, or that
has no declared failure policy is *silent calibration drift* — and silent
drift hides the one thing an honest instrument must expose: why this number,
and what happens when it is wrong.

This gate reads ``governance/CALIBRATIONS.yaml`` and fails closed unless every
registered calibration resolves:

  1.  the module file exists;
  2.  sha256(module) == registered ``source_sha256`` (drift lock — a silent
      edit to the calibration source fails CI until the registry and its
      acceptor are refreshed under a diff-bound change);
  3.  ``selected_value`` is present and non-empty;
  4.  ``sweep`` is present and non-empty (the value was selected, not guessed);
  5.  ``failure_policy`` is present and non-empty;
  6.  the ``acceptor`` exists AND binds the module in
      ``diff_scope.changed_files`` (the value cannot move without an acceptor).

Run::

    python scripts/ci/check_calibration_drift.py

Exit codes::

    0  — every governed calibration resolves; no silent drift
    1  — a drifted hash, a missing sweep / value / failure policy, or an
         unbound calibration
    2  — the registry itself is missing or malformed (fail-closed)
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "governance" / "CALIBRATIONS.yaml"

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass
class CalibrationReport:
    calibration_id: str
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def _sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _acceptor_binds(acceptor_path: Path, module: str) -> bool:
    try:
        data = yaml.safe_load(acceptor_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return False
    if not isinstance(data, dict):
        return False
    scope = data.get("diff_scope") or {}
    for entry in scope.get("changed_files") or []:
        if isinstance(entry, dict) and entry.get("path") == module:
            return True
    return False


def _non_empty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _check_calibration(cal: dict[str, Any]) -> CalibrationReport:
    cid = str(cal.get("id", "<unnamed>"))
    rep = CalibrationReport(calibration_id=cid)

    module_rel = cal.get("module")
    if not isinstance(module_rel, str) or not module_rel:
        rep.errors.append("missing 'module' field")
        return rep
    module_path = ROOT / module_rel
    if not module_path.is_file():
        rep.errors.append(f"module does not exist: {module_rel}")
        return rep

    declared = str(cal.get("source_sha256", ""))
    if not _SHA256.match(declared):
        rep.errors.append("missing/malformed 'source_sha256' (need 64 hex)")
    elif _sha256_of(module_path) != declared:
        rep.errors.append(
            f"calibration drift on {module_rel}: source hash changed "
            f"(refresh CALIBRATIONS.yaml + acceptor under a diff-bound change)"
        )

    if not _non_empty_str(cal.get("selected_value")):
        rep.errors.append("missing/empty 'selected_value'")
    if not _non_empty_str(cal.get("sweep")):
        rep.errors.append("missing/empty 'sweep' (no documented selection)")
    if not _non_empty_str(cal.get("failure_policy")):
        rep.errors.append("missing/empty 'failure_policy'")

    acc_rel = cal.get("acceptor")
    if not isinstance(acc_rel, str) or not (ROOT / acc_rel).is_file():
        rep.errors.append(f"acceptor does not exist: {acc_rel!r}")
    elif not _acceptor_binds(ROOT / acc_rel, module_rel):
        rep.errors.append(
            f"acceptor {acc_rel} does not bind {module_rel} in diff_scope.changed_files"
        )

    return rep


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=REGISTRY_PATH)
    args = parser.parse_args(argv)

    if not args.registry.is_file():
        print(f"FAIL: calibration registry not found: {args.registry}", file=sys.stderr)
        return 2
    try:
        registry = yaml.safe_load(args.registry.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        print(f"FAIL: registry is not valid YAML: {exc}", file=sys.stderr)
        return 2
    if not isinstance(registry, dict):
        print("FAIL: registry root must be a mapping", file=sys.stderr)
        return 2
    calibrations = registry.get("calibrations")
    if not isinstance(calibrations, list) or not calibrations:
        print("FAIL: registry 'calibrations' must be a non-empty list", file=sys.stderr)
        return 2

    reports = [_check_calibration(c) for c in calibrations if isinstance(c, dict)]
    failed = [r for r in reports if not r.ok]
    for rep in reports:
        print(f"[{'PASS' if rep.ok else 'FAIL'}] {rep.calibration_id}")
        for err in rep.errors:
            print(f"       - {err}")

    n = len(reports)
    if failed:
        print(
            f"\nFAIL: {len(failed)}/{n} calibrations show drift or missing governance",
            file=sys.stderr,
        )
        return 1
    print(f"\nOK: all {n} governed calibrations resolve; no silent drift")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
