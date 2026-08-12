#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Fail-closed gate for the operating-domain registry ``docs/math_boundaries.yaml``.

The registry declares, per estimator, the input conditions under which it is
valid / degraded / invalid (caller-facing operating domains — orthogonal to the
physics invariants in ``.claude/physics/INVARIANTS.yaml``). This gate enforces
that the registry stays honest and wired to reality:

* every entry declares ``id``/``name``/``source``/``invariants`` plus non-empty
  ``valid``/``degraded``/``invalid``/``falsifier`` text;
* every ``source`` path exists in the repository;
* every referenced ``INV-*`` exists in the canonical invariant registry (so a
  renamed/retired invariant can never leave a dangling domain reference);
* ``id`` values are unique.

Exit 0 ⇒ registry consistent; exit 1 ⇒ drift (with the offending entries named).
"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT: Path = Path(__file__).resolve().parents[2]
REGISTRY_PATH: Path = REPO_ROOT / "docs" / "math_boundaries.yaml"


def _load_collect_invariant_ids() -> Callable[..., list[str]]:
    """Load ``collect_invariant_ids`` from ``scripts/count_invariants.py`` by path.

    Importing ``scripts.count_invariants`` as a package only resolves when the
    repository root sits on ``sys.path`` — i.e. under ``pytest`` or
    ``python -m``. When this gate is invoked exactly as its shebang/acceptor
    documents, ``python scripts/ci/check_math_boundaries.py`` from the repo
    root, Python sets ``sys.path[0]`` to ``scripts/ci`` and the package import
    raises ``ModuleNotFoundError`` before a single check runs. We cannot patch
    that with ``sys.path.insert`` — the release-gate ``probe_b_path_hacks``
    fail-closes on any first-party ``sys.path`` mutation — and we must not
    re-implement the parser, because ``count_invariants`` is the single source
    of truth for the invariant set (the four-way drift it exists to prevent).
    Loading the sibling module by its absolute file path satisfies all three
    constraints with zero side effects on ``sys.path``.
    """
    module_path = REPO_ROOT / "scripts" / "count_invariants.py"
    spec = importlib.util.spec_from_file_location("geosync_count_invariants", module_path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise ImportError(f"cannot load invariant registry module at {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    collector: Callable[..., list[str]] = module.collect_invariant_ids
    return collector


_REQUIRED_TEXT_FIELDS: tuple[str, ...] = (
    "name",
    "source",
    "valid",
    "degraded",
    "invalid",
    "falsifier",
)


def _load_registry(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"math-boundaries registry not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("math-boundaries registry root must be a mapping")
    return data


def check_registry(
    registry: dict[str, Any], *, known_invariants: set[str], root: Path
) -> list[str]:
    """Return a list of consistency errors (empty ⇒ the registry is valid)."""
    errors: list[str] = []
    kernels = registry.get("kernels")
    if not isinstance(kernels, list) or not kernels:
        return ["registry.kernels must be a non-empty list"]

    seen_ids: set[str] = set()
    for i, kernel in enumerate(kernels):
        if not isinstance(kernel, dict):
            errors.append(f"kernels[{i}] must be a mapping")
            continue
        kid = kernel.get("id")
        label = kid if isinstance(kid, str) else f"index {i}"
        if not isinstance(kid, str) or not kid:
            errors.append(f"kernels[{i}] missing a string 'id'")
        elif kid in seen_ids:
            errors.append(f"duplicate kernel id '{kid}'")
        else:
            seen_ids.add(kid)

        for field in _REQUIRED_TEXT_FIELDS:
            value = kernel.get(field)
            if not isinstance(value, str) or not value.strip():
                errors.append(f"kernel '{label}': field '{field}' must be non-empty text")

        source = kernel.get("source")
        if isinstance(source, str) and source and not (root / source).exists():
            errors.append(f"kernel '{label}': source path does not exist: {source}")

        invariants = kernel.get("invariants")
        if not isinstance(invariants, list) or not invariants:
            errors.append(f"kernel '{label}': 'invariants' must be a non-empty list")
        else:
            for inv in invariants:
                if not isinstance(inv, str) or inv not in known_invariants:
                    errors.append(
                        f"kernel '{label}': references unknown invariant {inv!r} "
                        f"(not in .claude/physics/INVARIANTS.yaml)"
                    )
    return errors


def main(argv: list[str] | None = None) -> int:
    """Validate the math-boundaries registry; return 0 if consistent else 1."""
    try:
        registry = _load_registry(REGISTRY_PATH)
        known = set(_load_collect_invariant_ids()())
    except (FileNotFoundError, ValueError, yaml.YAMLError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    errors = check_registry(registry, known_invariants=known, root=REPO_ROOT)
    if errors:
        print("Math-boundaries registry gate FAILED:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    n_kernels = len(registry["kernels"])
    print(
        f"Math-boundaries registry passed: {n_kernels} kernels, all sources + invariants resolved."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
