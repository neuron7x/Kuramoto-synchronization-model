#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Fail-closed checker for the null-path inventory (Task 01).

Keeps ``docs/validation/NULL_PATH_INVENTORY.md`` honest: every generator and
claim-path it lists must point at a file that exists, and every entry must
declare a recognised class / adequacy. A vanished or relocated file fails the
gate, so the inventory cannot rot into a stale map. Makes no scientific claim.

Exit codes::

    0  inventory consistent with the tree
    1  drift (missing file, unknown class/adequacy, empty section)
    2  malformed invocation
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT = _ROOT / "docs" / "validation" / "NULL_PATH_INVENTORY.md"
_MARKER = "NULL-INVENTORY-DATA"
_GEN_CLASSES = frozenset({"IID", "STRUCTURE_PRESERVING"})
_ADEQUACY = frozenset(
    {
        "IID_INADEQUATE_FOR_AUTOCORRELATED",
        "IID_SYNTHETIC_DEMO_ONLY",
        "STRUCTURE_AGNOSTIC_OK",
        "STRUCTURE_PRESERVING_OK",
    }
)


def _extract(text: str) -> Any:
    m = text.find(_MARKER)
    if m == -1:
        raise SystemExit(f"inventory missing '{_MARKER}' marker")
    fence = text.find("```json", m)
    start = text.find("\n", fence) + 1
    end = text.find("```", start)
    if fence == -1 or end == -1:
        raise SystemExit("inventory json block malformed")
    try:
        return json.loads(text[start:end])
    except ValueError as exc:
        raise SystemExit(f"inventory json invalid: {exc}") from exc


def evaluate(data: dict[str, Any], root: Path) -> list[str]:
    errors: list[str] = []
    generators = data.get("generators")
    claim_paths = data.get("claim_paths")
    if not isinstance(generators, list) or not generators:
        errors.append("generators must be a non-empty list")
    if not isinstance(claim_paths, list) or not claim_paths:
        errors.append("claim_paths must be a non-empty list")
    for entry in generators or []:
        path = str(entry.get("path", ""))
        if not (root / path).exists():
            errors.append(f"generator {entry.get('name')}: missing file {path}")
        if entry.get("class") not in _GEN_CLASSES:
            errors.append(f"generator {entry.get('name')}: bad class {entry.get('class')!r}")
    for entry in claim_paths or []:
        path = str(entry.get("path", ""))
        if not (root / path).exists():
            errors.append(f"claim_path: missing file {path}")
        if entry.get("adequacy") not in _ADEQUACY:
            errors.append(f"claim_path {path}: bad adequacy {entry.get('adequacy')!r}")
    return errors


def main(argv: Sequence[str] | None = None, *, root: Path = _ROOT) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", default=str(_DEFAULT))
    args = parser.parse_args(argv)
    try:
        text = Path(args.inventory).read_text(encoding="utf-8")
    except OSError as exc:
        raise SystemExit(f"inventory unreadable: {exc}") from exc
    errors = evaluate(_extract(text), root)
    if errors:
        for e in errors:
            print(f"NULL-INVENTORY DRIFT: {e}", file=sys.stderr)
        return 1
    data = _extract(text)
    print(
        f"null-path inventory consistent: {len(data['generators'])} generators, "
        f"{len(data['claim_paths'])} claim paths verified present."
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
