#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Package-boundary ratchet — fail-closed, monotone-down wheel-surface ledger.

GeoSync's canonical wheel namespace is ``geosync*``. Today the wheel still ships
non-``geosync`` top-level packages (``core``, ``application``, ``scripts``,
``tools``, ...): nine console-script entry points still resolve into them, so a
one-shot ``packages.find = geosync*`` would break the installed CLI. The
canonical fix is the ADR-0024 migration (re-home runtime code under
``geosync.*``), which lands incrementally.

This ratchet makes that migration *safe and monotone* — the same doctrine the
import-architecture ratchet applies to ``src.*`` imports:

* a NEW non-``geosync`` top-level package entering the wheel surface fails the
  build — the leak set may never grow while migration is in flight;
* a package re-homed out of the surface also fails, with a one-line fix
  (``--write``) — paying down must tighten the ledger so it trends to empty.

GROUNDING: the leak set is measured by **building the wheel from a clean
``git archive HEAD``** and reading its actual top-level packages — exactly what
the release gate's ``B.wheel`` probe checks. ``packages.find.include`` *does*
control the wheel surface (verified: dropping ``markets``/``sandbox`` from
``include`` and building clean drops them, 16 -> 14). We still measure the built
wheel rather than parse ``include`` because (a) ``include`` alone misses files
pulled in by other means — e.g. ``[tool.setuptools_scm].version_file`` causes a
stray ``src`` top-level to ship even when ``src`` is not in ``include`` — and
(b) it is immune to the local-dev hazard that a STALE ``build/`` directory
(setuptools ``build_py`` reuses ``build/lib`` without cleaning) silently injects
old packages into ``pip wheel .`` runs. Building from a fresh ``git archive``
tempdir sidesteps both. The wheel is the only truth.

Usage::

    python scripts/ci/check_package_boundary.py            # verify
    python scripts/ci/check_package_boundary.py --write     # tighten ledger

Exit codes::

    0  — current leak set == baseline (no new leak, no stale entry)
    1  — a new non-geosync package entered, or a re-homed entry is stale
    2  — the wheel could not be built (cannot establish the surface; fail-closed)
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASELINE_PATH = ROOT / ".github" / "package_boundary_baseline.json"


class WheelBuildError(RuntimeError):
    """Raised when the clean-room wheel cannot be built."""


def _shipped_leak() -> set[str]:
    """Non-geosync top-level packages the wheel actually ships.

    Builds the wheel from a clean ``git archive HEAD`` (no working-tree cruft,
    no stale egg-info) and reads the real top-level package names — the same
    measurement as release_gate's B.wheel probe. Raises WheelBuildError if the
    build fails (the surface cannot be established → fail closed).
    """
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        arch = tdp / "src.tar"
        with arch.open("wb") as fh:
            subprocess.run(
                ["git", "archive", "--format=tar", "HEAD"],
                cwd=ROOT,
                stdout=fh,
                check=True,
            )
        srcdir = tdp / "src_tree"
        srcdir.mkdir()
        subprocess.run(["tar", "-xf", str(arch), "-C", str(srcdir)], check=True)
        wheeldir = tdp / "wheel"
        build = subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "wheel",
                "--no-deps",
                "--no-cache-dir",
                "-w",
                str(wheeldir),
                str(srcdir),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        wheels = list(wheeldir.glob("*.whl"))
        if build.returncode != 0 or not wheels:
            raise WheelBuildError(build.stderr[-600:] or "wheel build produced no artifact")
        with zipfile.ZipFile(wheels[0]) as zf:
            tops = {n.split("/")[0] for n in zf.namelist()}
        return {
            top for top in tops if not top.endswith(".dist-info") and not top.startswith("geosync")
        }


def _load_baseline() -> set[str]:
    if not BASELINE_PATH.exists():
        return set()
    payload = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    return set(payload.get("non_geosync_packages", []))


def _write_baseline(leak: set[str]) -> None:
    existing = {}
    if BASELINE_PATH.exists():
        existing = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    payload = {
        "_doc": existing.get(
            "_doc",
            "Package-boundary debt ledger (RATCHET). Non-geosync top-level "
            "packages still shipped in the built wheel. This set may ONLY "
            "shrink; check_package_boundary.py enforces it by building the wheel "
            "from git archive HEAD. Target: empty (single geosync* namespace, "
            "release-gate B.wheel GREEN).",
        ),
        "version": 2,
        "measured_by": "wheel-build (git archive HEAD)",
        "non_geosync_packages": sorted(leak),
    }
    BASELINE_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def evaluate(cur: set[str], base: set[str]) -> tuple[bool, list[str], list[str]]:
    """Pure ratchet comparison. Returns (failed, new_leaks, fixed)."""
    new = sorted(cur - base)
    fixed = sorted(base - cur)
    return (bool(new or fixed), new, fixed)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Package-boundary ratchet.")
    parser.add_argument(
        "--write",
        action="store_true",
        help="Regenerate the baseline from the current built wheel (tighten the ledger).",
    )
    args = parser.parse_args(argv)

    try:
        cur = _shipped_leak()
    except (WheelBuildError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: could not build wheel to measure surface: {exc}", file=sys.stderr)
        return 2

    if args.write:
        _write_baseline(cur)
        print(f"Baseline tightened: {len(cur)} non-geosync packages in the built wheel.")
        return 0

    base = _load_baseline()
    failed, new, fixed = evaluate(cur, base)

    if new:
        print("ERROR: new package-boundary debt (the geosync* wheel ratchet only shrinks).")
        for pkg in new:
            print(f"  + non-geosync package in wheel: {pkg}")
        print("Fix: re-home the module under the canonical `geosync` namespace.")

    if fixed:
        print(
            f"Boundary paid down ({len(fixed)} package(s) re-homed) but the ledger "
            "is stale. Tighten it so it stays honest:"
        )
        print("  python scripts/ci/check_package_boundary.py --write")

    if not failed:
        print(
            f"Package-boundary ratchet held: {len(cur)} non-geosync packages in the "
            "built wheel (target 0). No new debt."
        )
        if not cur:
            print("Ledger empty — single canonical geosync* wheel achieved.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
