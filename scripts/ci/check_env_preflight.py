# SPDX-License-Identifier: MIT
"""Canonical Python 3.12 environment preflight (ENV-001).

Gatekeeper for the TST / ARC / PKG waves. This script is the *descriptor +
preflight* half of the environment story; building a true hermetic container is
ENV-005's job. This gate answers one question, fail-closed:

    Is the interpreter a Python 3.12 with pandas >= 2.3.3 and every required
    project dependency actually installed and resolvable?

Design notes
------------
* No reliance on any "audit shim". The checker resolves dependency versions
  directly from ``importlib.metadata`` (the real installed distribution
  metadata) and reads the requirement floors straight from ``requirements.txt``.
  It does not import ``sitecustomize`` monkeypatches, stub modules, or any
  compatibility shim to decide whether the environment is healthy.
* ``evaluate_env`` is a pure function over a plain descriptor dict so tests can
  inject a doctored environment (sub-floor pandas, a missing dependency) and
  assert the gate fails closed.

Severity model
--------------
HARD failures (exit code 1 — the fail-closed contract):
    * interpreter is not Python 3.12.x
    * pandas is missing or below the named floor (>= 2.3.3)
    * any required dependency is not installed / not resolvable

DEVIATIONS (reported, non-fatal unless ``--strict``):
    * a required dependency is installed but below its ``requirements.txt``
      floor. On this pre-hermetic sandbox several security-hardened floors are
      not yet met; those belong to ENV-005's hermetic container, not to the
      descriptor gate. ``--strict`` promotes every deviation to a HARD failure
      so the same gate can certify a hermetic image.
"""

from __future__ import annotations

import argparse
import importlib.metadata as importlib_metadata
import json
import platform
import sys
from pathlib import Path
from typing import Any

from packaging.requirements import Requirement
from packaging.version import Version

ROOT = Path(__file__).resolve().parents[2]
REQUIREMENTS = ROOT / "requirements.txt"

# ENV-001 hard contract.
REQUIRED_PYTHON = (3, 12)
PANDAS_MIN = "2.3.3"

# Curated, deterministic subset of x86-64 CPU capability flags worth recording
# for reproducibility (SIMD width drives numpy/torch/numba code paths).
_CPU_FLAGS_OF_INTEREST = (
    "sse2",
    "sse4_1",
    "sse4_2",
    "avx",
    "avx2",
    "avx512f",
    "fma",
    "f16c",
    "bmi1",
    "bmi2",
)


def parse_required(requirements_path: Path = REQUIREMENTS) -> list[Requirement]:
    """Parse the direct required dependencies from ``requirements.txt``."""
    reqs: list[Requirement] = []
    for raw in requirements_path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        reqs.append(Requirement(line))
    return reqs


def _resolved_version(name: str) -> str | None:
    try:
        return importlib_metadata.version(name)
    except importlib_metadata.PackageNotFoundError:
        return None


def _cpu_flags() -> list[str]:
    try:
        text = Path("/proc/cpuinfo").read_text(encoding="utf-8")
    except OSError:
        return []
    for line in text.splitlines():
        if line.startswith("flags") or line.startswith("Features"):
            present = set(line.split(":", 1)[1].split())
            return [f for f in _CPU_FLAGS_OF_INTEREST if f in present]
    return []


def build_descriptor(requirements_path: Path = REQUIREMENTS) -> dict[str, Any]:
    """Capture the canonical environment descriptor for this interpreter."""
    vi = sys.version_info
    libc_name, libc_ver = platform.libc_ver()
    resolved: dict[str, str | None] = {}
    for req in parse_required(requirements_path):
        resolved[req.name] = _resolved_version(req.name)
    return {
        "schema": "geosync.env.descriptor/1",
        "descriptor_id": "python312",
        "role": "ENV-001 canonical environment descriptor + preflight target",
        "python": {
            "version": platform.python_version(),
            "major": vi.major,
            "minor": vi.minor,
            "micro": vi.micro,
            "implementation": platform.python_implementation(),
            "compiler": platform.python_compiler(),
            "executable": sys.executable,
        },
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "libc": {"name": libc_name, "version": libc_ver},
            "cpu_flags": _cpu_flags(),
        },
        "required_dependencies": {
            "count": len(resolved),
            "pandas_floor": PANDAS_MIN,
            "python_floor": f"{REQUIRED_PYTHON[0]}.{REQUIRED_PYTHON[1]}",
            "resolved": resolved,
            "specifiers": {
                req.name: str(req.specifier) for req in parse_required(requirements_path)
            },
        },
    }


def evaluate_env(
    descriptor: dict[str, Any],
    requirements: list[Requirement],
    *,
    strict: bool = False,
) -> tuple[bool, dict[str, Any]]:
    """Pure evaluation of a descriptor against the required deps.

    Returns ``(ok, report)``. ``ok`` is False (fail-closed) whenever a HARD
    invariant is violated, or — under ``strict`` — when any below-floor
    deviation is present.
    """
    hard_failures: list[str] = []
    deviations: list[dict[str, str]] = []
    missing: list[str] = []

    py = descriptor["python"]
    if (py["major"], py["minor"]) != REQUIRED_PYTHON:
        hard_failures.append(
            f"python: expected {REQUIRED_PYTHON[0]}.{REQUIRED_PYTHON[1]}.x, "
            f"got {py['major']}.{py['minor']}.{py.get('micro', '?')}"
        )

    resolved: dict[str, str | None] = descriptor["required_dependencies"]["resolved"]

    # pandas is the named gatekeeper floor: HARD.
    pandas_ver = resolved.get("pandas")
    if pandas_ver is None:
        hard_failures.append("pandas: not installed (required floor >= " + PANDAS_MIN + ")")
    elif Version(pandas_ver) < Version(PANDAS_MIN):
        hard_failures.append(f"pandas: {pandas_ver} < required floor {PANDAS_MIN}")

    for req in requirements:
        ver = resolved.get(req.name)
        if ver is None:
            missing.append(req.name)
            continue
        if req.specifier and not req.specifier.contains(ver, prereleases=True):
            deviations.append(
                {"name": req.name, "installed": ver, "specifier": str(req.specifier)}
            )

    for name in missing:
        hard_failures.append(f"missing required dependency: {name}")

    if strict:
        for dev in deviations:
            hard_failures.append(
                f"below floor (strict): {dev['name']} {dev['installed']} "
                f"does not satisfy {dev['specifier']}"
            )

    ok = not hard_failures
    report = {
        "ok": ok,
        "strict": strict,
        "python_ok": (py["major"], py["minor"]) == REQUIRED_PYTHON,
        "pandas_ok": pandas_ver is not None and Version(pandas_ver) >= Version(PANDAS_MIN),
        "pandas_version": pandas_ver,
        "required_count": len(requirements),
        "present_count": sum(1 for r in requirements if resolved.get(r.name) is not None),
        "missing": missing,
        "below_floor_deviations": deviations,
        "hard_failures": hard_failures,
    }
    return ok, report


def _render(report: dict[str, Any]) -> str:
    lines: list[str] = []
    status = "PASS" if report["ok"] else "FAIL"
    lines.append(f"ENV-001 preflight: {status} (strict={report['strict']})")
    lines.append(
        f"  python 3.12: {'ok' if report['python_ok'] else 'FAIL'}; "
        f"pandas {report['pandas_version']} >= {PANDAS_MIN}: "
        f"{'ok' if report['pandas_ok'] else 'FAIL'}"
    )
    lines.append(
        f"  required deps present: {report['present_count']}/{report['required_count']}"
    )
    if report["missing"]:
        lines.append(f"  MISSING (hard): {', '.join(report['missing'])}")
    if report["below_floor_deviations"]:
        lines.append(
            f"  below-floor deviations ({len(report['below_floor_deviations'])}) "
            f"— ENV-005 hermetic-container territory, non-fatal unless --strict:"
        )
        for dev in report["below_floor_deviations"]:
            lines.append(f"      - {dev['name']} {dev['installed']} !~ {dev['specifier']}")
    if report["hard_failures"]:
        lines.append("  HARD FAILURES:")
        for hf in report["hard_failures"]:
            lines.append(f"      - {hf}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ENV-001 canonical env preflight.")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="promote below-floor deviations to hard failures (hermetic image gate).",
    )
    parser.add_argument(
        "--emit-descriptor",
        type=Path,
        default=None,
        metavar="PATH",
        help="write the full environment descriptor JSON to PATH and exit 0.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print the preflight report as JSON instead of text.",
    )
    args = parser.parse_args(argv)

    descriptor = build_descriptor()

    if args.emit_descriptor is not None:
        args.emit_descriptor.parent.mkdir(parents=True, exist_ok=True)
        args.emit_descriptor.write_text(
            json.dumps(descriptor, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(f"wrote descriptor -> {args.emit_descriptor}")
        return 0

    ok, report = evaluate_env(descriptor, parse_required(), strict=args.strict)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(_render(report))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
