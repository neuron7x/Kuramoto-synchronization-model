#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Hierarchical repository-health sensor.

One machine-readable JSON state for the whole repository, built by rolling
several independent surface sub-sensors up under a single fail-closed
status with OK / WARN / RED / UNKNOWN semantics.

The contract is deliberately small and honest: the sensor *classifies*
drift, it does not repair it, and it never promotes the unknown into a
pass. Aggregation is worst-wins — RED dominates UNKNOWN dominates WARN
dominates OK — so a single red sub-sensor cannot be averaged away, and a
single unknown is never silently treated as healthy.

Read-only and offline: it inspects files, it does not execute the system.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

OK = "OK"
WARN = "WARN"
RED = "RED"
UNKNOWN = "UNKNOWN"

# Worst-wins precedence (highest index = most severe).
_PRECEDENCE = (OK, WARN, UNKNOWN, RED)


def worst(statuses: list[str]) -> str:
    """Return the most severe status; OK only when every input is OK."""
    if not statuses:
        return UNKNOWN
    return max(statuses, key=_PRECEDENCE.index)


@dataclass(frozen=True)
class Row:
    name: str
    status: str
    detail: str
    path: str


@dataclass(frozen=True)
class Section:
    name: str
    status: str
    counts: dict[str, int]
    rows: list[Row]


def _count(rows: list[Row]) -> dict[str, int]:
    counts = {OK: 0, WARN: 0, RED: 0, UNKNOWN: 0}
    for row in rows:
        counts[row.status] += 1
    return counts


def _section(name: str, rows: list[Row]) -> Section:
    return Section(name, worst([r.status for r in rows]), _count(rows), rows)


# --------------------------------------------------------------------------
# Sub-sensors. Each returns a Section. All are read-only and deterministic.
# --------------------------------------------------------------------------
def mfn_surface(root: Path) -> Section:
    """Delegate to the existing MFN surface checker, re-rolled as a section."""
    module_path = root / "tools" / "mfn_surface_check.py"
    if not module_path.exists():
        return _section(
            "mfn_surface",
            [Row("mfn_surface_check", UNKNOWN, "checker missing", "tools/mfn_surface_check.py")],
        )
    spec = importlib.util.spec_from_file_location("mfn_surface_check", module_path)
    if spec is None or spec.loader is None:  # pragma: no cover - import guard
        return _section(
            "mfn_surface", [Row("mfn_surface_check", UNKNOWN, "import failed", str(module_path))]
        )
    module = importlib.util.module_from_spec(spec)
    # Register before exec so dataclasses in the loaded module resolve their
    # own module namespace (otherwise dataclass() raises on KW_ONLY lookup).
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    raw_rows: list[Any] = list(module.collect(root))
    rows = [Row(str(r.name), str(r.status), str(r.detail), str(r.path)) for r in raw_rows]
    return _section("mfn_surface", rows)


def reproducible_capsules(root: Path) -> Section:
    """Every capsule bundle must carry its reproduction triad."""
    base = root / "artifacts" / "reproducible_capsules"
    required = ("SHA256SUMS", "manifest.json", "runbook.md")
    if not base.exists():
        return _section(
            "reproducible_capsules",
            [Row("capsules_root", UNKNOWN, "no capsules dir", "artifacts/reproducible_capsules")],
        )
    rows: list[Row] = []
    for bundle in sorted(base.glob("*/bundle")):
        rel = str(bundle.relative_to(root))
        missing = [f for f in required if not (bundle / f).exists()]
        if missing:
            rows.append(Row(bundle.parent.name, RED, "missing: " + ", ".join(missing), rel))
        else:
            rows.append(Row(bundle.parent.name, OK, "reproduction triad present", rel))
    if not rows:
        rows.append(Row("capsules", UNKNOWN, "no bundles found", str(base.relative_to(root))))
    return _section("reproducible_capsules", rows)


def package_entrypoints(root: Path) -> Section:
    """Declared console scripts must point at modules that exist on disk."""
    rel = "pyproject.toml"
    pyproject = root / rel
    if not pyproject.exists():
        return _section("package_entrypoints", [Row("pyproject", UNKNOWN, "missing file", rel)])
    text = pyproject.read_text(encoding="utf-8")
    if "[project.scripts]" not in text:
        return _section(
            "package_entrypoints", [Row("project.scripts", UNKNOWN, "no scripts table", rel)]
        )
    block = text.split("[project.scripts]", 1)[1]
    block = block.split("\n[", 1)[0]
    rows: list[Row] = []
    for line in block.splitlines():
        if "=" not in line or ":" not in line:
            continue
        name, target = (part.strip() for part in line.split("=", 1))
        dotted = target.strip().strip('"').strip("'").split(":", 1)[0]
        mod_path = root / (dotted.replace(".", "/") + ".py")
        pkg_path = root / dotted.replace(".", "/") / "__init__.py"
        if mod_path.exists() or pkg_path.exists():
            rows.append(Row(name, OK, "module resolves", dotted))
        else:
            rows.append(Row(name, RED, "module not found", dotted))
    if not rows:
        rows.append(Row("project.scripts", UNKNOWN, "no entries parsed", rel))
    return _section("package_entrypoints", rows)


SUB_SENSORS: tuple[Callable[[Path], Section], ...] = (
    mfn_surface,
    reproducible_capsules,
    package_entrypoints,
)


def collect(root: Path) -> list[Section]:
    return [sensor(root) for sensor in SUB_SENSORS]


def payload(sections: list[Section]) -> dict[str, object]:
    rollup = {OK: 0, WARN: 0, RED: 0, UNKNOWN: 0}
    for section in sections:
        for status, n in section.counts.items():
            rollup[status] += n
    status = worst([s.status for s in sections])
    return {
        "status": status,
        "counts": rollup,
        "sections": [asdict(s) for s in sections],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="exit non-zero unless overall status is OK or WARN",
    )
    args = parser.parse_args(argv)
    result = payload(collect(Path(args.root).resolve()))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if args.strict and result["status"] not in {OK, WARN} else 0


if __name__ == "__main__":
    raise SystemExit(main())
