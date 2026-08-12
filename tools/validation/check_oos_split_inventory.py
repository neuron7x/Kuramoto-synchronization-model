#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Fail-closed regression guard for the OOS-split inventory (Task 16).

Keeps docs/validation/OOS_SPLIT_INVENTORY.md honest: every listed split path
must exist and must still contain its declared leakage-protection marker
(``embargo``, ``look-ahead``, ...). A path that loses its marker — e.g. someone
removes the embargo from a claim-bearing OOS path — fails the gate. A null
marker means the path is structurally safe (global aggregate, no boundary
predictor) and carries no token requirement. Makes no scientific claim.

Exit codes::

    0  inventory consistent (every protected path retains its marker)
    1  drift (missing file, lost protection marker, unknown protection)
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
_DEFAULT = _ROOT / "docs" / "validation" / "OOS_SPLIT_INVENTORY.md"
_MARKER = "OOS-SPLIT-DATA"
_PROTECTIONS = frozenset({"EMBARGO", "LOOKAHEAD_LAG", "GLOBAL_AGGREGATE_NO_BOUNDARY_LEAK"})


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
    splits = data.get("splits")
    if not isinstance(splits, list) or not splits:
        errors.append("splits must be a non-empty list")
        return errors
    for entry in splits:
        path = str(entry.get("path", ""))
        protection = entry.get("protection")
        marker = entry.get("marker")
        target = root / path
        if not target.exists():
            errors.append(f"split path missing: {path}")
            continue
        if protection not in _PROTECTIONS:
            errors.append(f"{path}: unknown protection {protection!r}")
        if marker is not None:
            if str(marker).lower() not in target.read_text(encoding="utf-8").lower():
                errors.append(
                    f"{path}: declared protection marker '{marker}' is GONE "
                    "(leakage protection may have been removed)"
                )
    return errors


def main(argv: Sequence[str] | None = None, *, root: Path = _ROOT) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", default=str(_DEFAULT))
    args = parser.parse_args(argv)
    try:
        text = Path(args.inventory).read_text(encoding="utf-8")
    except OSError as exc:
        raise SystemExit(f"inventory unreadable: {exc}") from exc
    data = _extract(text)
    errors = evaluate(data, root)
    if errors:
        for e in errors:
            print(f"OOS-SPLIT DRIFT: {e}", file=sys.stderr)
        return 1
    print(f"OOS-split inventory consistent: {len(data['splits'])} split paths, all protected.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
