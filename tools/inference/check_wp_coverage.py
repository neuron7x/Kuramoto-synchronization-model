#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Fail-closed checker for the Inference-Legend work-package coverage ledger.

``docs/INFERENCE_LEGEND_EXIT_WORK_ACT.md`` defines ten work packages (WP-01..10)
on the route from a hypothesis-tier system to a reproducible research artifact.
Most of those packages are NOT greenfield — GeoSync already ships substantial
substrate (claim-maturity ladder, null/baseline generators, walk-forward + SPA
OOS, the fused Kuramoto-Ricci kernel, market-state contract). The coverage
ledger ``docs/INFERENCE_LEGEND_WP_COVERAGE.md`` records, per work package, which
existing artifacts implement it and which gaps remain — so the act binds to
reality instead of spawning a duplicate stack.

This gate keeps that ledger honest. It parses the machine-readable block and
fails closed when:

* an ``EXISTS`` / ``PARTIAL`` work package references an artifact path that is
  not present in the tree (the map has rotted — an artifact moved or was
  deleted while the ledger still claims coverage);
* a ``GAP`` work package lists implementation artifacts (a gap with code is not
  a gap);
* the block is missing a work package id WP-01..WP-10, repeats one, or uses an
  unknown status.

A coverage claim is therefore falsifiable: it survives only while the artifacts
it cites really exist. The gate makes no scientific claim — it asserts
structural correspondence between the ledger and the repository, nothing about
predictive rank.

Exit codes::

    0  ledger consistent with the tree
    1  drift (missing artifact, gap-with-code, id/status error)
    2  malformed invocation (file/marker/JSON unreadable)
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_LEDGER = _ROOT / "docs" / "INFERENCE_LEGEND_WP_COVERAGE.md"
_MARKER = "WP-COVERAGE-DATA"
_VALID_STATUS = frozenset({"EXISTS", "PARTIAL", "GAP"})
_EXPECTED_IDS = tuple(f"WP-{i:02d}" for i in range(1, 11))


@dataclass
class Result:
    errors: list[str] = field(default_factory=list)
    checked_artifacts: int = 0


def _extract_block(text: str) -> Any:
    marker = text.find(_MARKER)
    if marker == -1:
        raise SystemExit(f"coverage ledger missing '{_MARKER}' marker")
    fence = text.find("```json", marker)
    if fence == -1:
        raise SystemExit("coverage ledger missing fenced json block after marker")
    start = text.find("\n", fence) + 1
    end = text.find("```", start)
    if end == -1:
        raise SystemExit("coverage ledger json block is unterminated")
    try:
        return json.loads(text[start:end])
    except ValueError as exc:
        raise SystemExit(f"coverage ledger json is invalid: {exc}") from exc


def evaluate(data: dict[str, Any], root: Path) -> Result:
    result = Result()
    packages = data.get("work_packages")
    if not isinstance(packages, list) or not packages:
        result.errors.append("work_packages must be a non-empty list")
        return result

    seen: set[str] = set()
    for entry in packages:
        if not isinstance(entry, dict):
            result.errors.append("each work_package must be a mapping")
            continue
        wp_id = str(entry.get("id", "")).strip()
        status = str(entry.get("status", "")).strip()
        artifacts = entry.get("artifacts", [])
        if wp_id in seen:
            result.errors.append(f"{wp_id}: duplicate work-package id")
        seen.add(wp_id)
        if status not in _VALID_STATUS:
            result.errors.append(f"{wp_id}: status {status!r} not in {sorted(_VALID_STATUS)}")
        if not isinstance(artifacts, list):
            result.errors.append(f"{wp_id}: artifacts must be a list")
            continue
        if status == "GAP" and artifacts:
            result.errors.append(f"{wp_id}: GAP must list no implementation artifacts")
        for rel in artifacts:
            rel_str = str(rel)
            result.checked_artifacts += 1
            if not (root / rel_str).exists():
                result.errors.append(f"{wp_id}: claimed artifact does not exist: {rel_str}")

    missing_ids = [i for i in _EXPECTED_IDS if i not in seen]
    if missing_ids:
        result.errors.append("missing work-package ids: " + ", ".join(missing_ids))
    return result


def main(argv: Sequence[str] | None = None, *, root: Path = _ROOT) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", default=str(_DEFAULT_LEDGER))
    args = parser.parse_args(argv)

    ledger = Path(args.ledger)
    try:
        text = ledger.read_text(encoding="utf-8")
    except OSError as exc:
        raise SystemExit(f"coverage ledger unreadable: {exc}") from exc

    data = _extract_block(text)
    result = evaluate(data, root)
    if result.errors:
        for err in result.errors:
            print(f"WP-COVERAGE DRIFT: {err}", file=sys.stderr)
        return 1
    print(
        f"WP coverage ledger consistent: {len(_EXPECTED_IDS)} packages, "
        f"{result.checked_artifacts} artifacts verified present."
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
