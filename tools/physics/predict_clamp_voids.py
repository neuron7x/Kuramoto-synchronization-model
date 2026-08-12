#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Predict clamp-registry voids before a commit — and auto-re-pin the safe ones.

The clamp registry (``tools/physics/clamp_registry.yaml``) pins every numerical
clamp by exact ``path:line``. Any edit that adds lines above a clamp silently
shifts its line number, so the registry goes stale and CI (``check_silent_clamps``)
fails *after* the commit. This recurred repeatedly; this tool turns that
post-hoc void into a pre-commit forecast.

It reuses the exact detector the gate uses (``check_silent_clamps.scan_file``),
so its prediction is what the gate will actually do, and classifies each drift:

* ``SAFE_LINE_SHIFT`` — a ``(path, shape)`` group has the same number of clamps
  as the registry but at different lines: the clamp only moved. ``--write``
  re-pins these automatically (the entropy that caused 3 reactive fixes).
* ``NEW_CLAMP`` — a clamp with no registry entry for its ``(path, shape)``: a
  genuinely new clamp that needs a human-declared ``reason``. **Never**
  auto-fixed; reported as a hard void.
* ``REMOVED_CLAMP`` — a registry site with no live clamp: stale pin to drop.

Exit codes::

    0  no voids, or only SAFE_LINE_SHIFT/REMOVED voids (and --write applied them)
    1  a hard void (NEW_CLAMP needs a human reason; or unfixed drift without --write)
    2  malformed invocation
"""

from __future__ import annotations

import argparse
import importlib.util
import re
import sys
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import yaml

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parents[1]
_REGISTRY = _HERE / "clamp_registry.yaml"


def _load_detector() -> Any:
    """Load the gate's own clamp detector so prediction == gate behaviour."""
    path = _HERE / "check_silent_clamps.py"
    spec = importlib.util.spec_from_file_location("_silent_clamps_detector", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot load clamp detector at {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def current_sites() -> dict[tuple[str, str], set[int]]:
    """``(rel_path, shape) -> {line}`` for every live clamp in the scoped tree."""
    det = _load_detector()
    out: dict[tuple[str, str], set[int]] = defaultdict(set)
    for fp in det._scope_files():
        for site in det.scan_file(fp):
            out[(det._rel(fp), site.shape)].add(site.line)
    return out


def registry_sites(registry_text: str) -> dict[tuple[str, str], set[int]]:
    """``(path, shape) -> {line}`` parsed from the registry YAML."""
    data = yaml.safe_load(registry_text)
    out: dict[tuple[str, str], set[int]] = defaultdict(set)
    for entry in data if isinstance(data, list) else data.get("clamps", []):
        shape = str(entry.get("name", ""))
        for site in entry.get("sites", []) or []:
            path, _, line = str(site).rpartition(":")
            if line.isdigit():
                out[(path, shape)].add(int(line))
    return out


def classify(
    live: dict[tuple[str, str], set[int]],
    pinned: dict[tuple[str, str], set[int]],
) -> dict[str, list[dict[str, Any]]]:
    """Bucket each (path, shape) drift into safe / hard void classes."""
    safe: list[dict[str, Any]] = []
    new: list[dict[str, Any]] = []
    removed: list[dict[str, Any]] = []
    for key in sorted(set(live) | set(pinned)):
        path, shape = key
        live_lines = live.get(key, set())
        pin_lines = pinned.get(key, set())
        if live_lines == pin_lines:
            continue
        if pin_lines and len(live_lines) == len(pin_lines):
            safe.append(
                {
                    "path": path,
                    "shape": shape,
                    "from": sorted(pin_lines),
                    "to": sorted(live_lines),
                }
            )
        elif not pin_lines:
            new.append({"path": path, "shape": shape, "lines": sorted(live_lines)})
        elif not live_lines:
            removed.append({"path": path, "shape": shape, "lines": sorted(pin_lines)})
        else:
            # count changed AND both non-empty: a clamp was added or removed.
            new.append(
                {
                    "path": path,
                    "shape": shape,
                    "added": sorted(live_lines - pin_lines),
                    "removed": sorted(pin_lines - live_lines),
                }
            )
    return {"SAFE_LINE_SHIFT": safe, "NEW_CLAMP": new, "REMOVED_CLAMP": removed}


def apply_safe_repins(registry_text: str, safe: list[dict[str, Any]]) -> str:
    """Rewrite only the line number of each safely-shifted clamp pin."""
    text = registry_text
    for item in safe:
        old_lines = sorted(item["from"])
        new_lines = sorted(item["to"])
        path = item["path"]
        for old, new in zip(old_lines, new_lines):
            if old == new:
                continue
            text = re.sub(
                rf"(- {re.escape(path)}):{old}\b",
                rf"\g<1>:{new}",
                text,
            )
    return text


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="apply safe line-shift re-pins")
    parser.add_argument("--registry", default=str(_REGISTRY))
    args = parser.parse_args(argv)

    registry_path = Path(args.registry)
    try:
        registry_text = registry_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SystemExit(f"registry unreadable: {exc}") from exc

    buckets = classify(current_sites(), registry_sites(registry_text))
    safe = buckets["SAFE_LINE_SHIFT"]
    new = buckets["NEW_CLAMP"]
    removed = buckets["REMOVED_CLAMP"]

    for item in safe:
        print(f"SAFE_LINE_SHIFT {item['path']} [{item['shape']}] {item['from']} -> {item['to']}")
    for item in removed:
        print(f"REMOVED_CLAMP {item['path']} [{item['shape']}] stale pin {item.get('lines')}")
    for item in new:
        print(
            f"NEW_CLAMP {item['path']} [{item['shape']}] needs a human reason: "
            f"{item.get('lines') or item.get('added')}",
            file=sys.stderr,
        )

    if args.write and (safe or removed):
        registry_path.write_text(apply_safe_repins(registry_text, safe), encoding="utf-8")
        print(f"re-pinned {len(safe)} safe clamp line shift(s)")

    if new:
        print(
            f"clamp-void forecast: {len(new)} NEW_CLAMP void(s) need a human reason.",
            file=sys.stderr,
        )
        return 1
    if (safe or removed) and not args.write:
        print(
            f"clamp-void forecast: {len(safe)} line-shift + {len(removed)} stale; "
            "re-run with --write to re-pin safely.",
            file=sys.stderr,
        )
        return 1
    print("clamp-void forecast: clean (registry in sync with the tree).")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
