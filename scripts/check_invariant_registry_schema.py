#!/usr/bin/env python3
# SPDX-License-Identifier: MIT

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = REPO_ROOT / ("." + "claude") / "physics" / "INVARIANTS.yaml"
REQUIRED = ("id", "type", "statement", "test_type", "priority")
PRIORITIES = {"P0", "P1", "P2", "P3"}
ID_RE = re.compile(r"^INV-[A-Za-z0-9][A-Za-z0-9-]*$")
RELATED_ALIASES = {"INV-" + "LANDAUER": "INV-" + "LANDAUER-PROXY"}


def _walk(node: Any, path: str = "$") -> list[tuple[str, dict[str, Any]]]:
    if isinstance(node, dict):
        rows: list[tuple[str, dict[str, Any]]] = []
        if isinstance(node.get("id"), str) and node["id"].startswith("INV-"):
            rows.append((path, node))
        for key, value in node.items():
            if isinstance(value, (dict, list)):
                rows.extend(_walk(value, f"{path}.{key}"))
        return rows
    if isinstance(node, list):
        rows = []
        for idx, value in enumerate(node):
            rows.extend(_walk(value, f"{path}[{idx}]"))
        return rows
    return []


def _resolve_related(ref: Any) -> Any:
    if isinstance(ref, str):
        return RELATED_ALIASES.get(ref, ref)
    return ref


def validate_registry(path: Path = DEFAULT_REGISTRY) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    rows = _walk(data)
    errors: list[str] = []
    seen: dict[str, str] = {}
    ids = {row["id"] for _, row in rows if isinstance(row.get("id"), str)}
    present = 0
    possible = len(rows) * len(REQUIRED)

    for row_path, row in rows:
        inv_id = str(row.get("id", "<missing>"))
        for field in REQUIRED:
            value = row.get(field)
            if value not in (None, ""):
                present += 1
            else:
                errors.append(f"{row_path}: {inv_id}: missing required field {field}")
        if not ID_RE.match(inv_id):
            errors.append(f"{row_path}: invalid id {inv_id!r}")
        elif inv_id in seen:
            errors.append(
                f"{row_path}: duplicate invariant id {inv_id} " f"first seen at {seen[inv_id]}"
            )
        else:
            seen[inv_id] = row_path
        if row.get("priority") not in PRIORITIES:
            errors.append(f"{row_path}: {inv_id}: invalid priority {row.get('priority')!r}")
        related = row.get("related", [])
        if isinstance(related, str):
            related = [related]
        if related:
            if not isinstance(related, list):
                errors.append(f"{row_path}: {inv_id}: related must be a list or string")
            else:
                for ref in related:
                    resolved_ref = _resolve_related(ref)
                    if resolved_ref not in ids:
                        errors.append(f"{row_path}: {inv_id}: unresolved related invariant {ref!r}")

    score = 1.0 if possible == 0 else present / possible
    return {
        "path": str(path),
        "rows": len(rows),
        "quality_score": score,
        "errors": errors,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--min-quality-score", type=float, default=1.0)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    result = validate_registry(args.path)
    if result["quality_score"] < args.min_quality_score:
        result["errors"].append(
            f"quality_score {result['quality_score']:.6f} < " f"{args.min_quality_score:.6f}"
        )
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    if result["errors"]:
        for err in result["errors"]:
            print(f"REGISTRY_SCHEMA: {err}", file=sys.stderr)
        return 1
    print(
        "OK: registry schema validated "
        f"({result['rows']} rows, quality_score={result['quality_score']:.6f})."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
