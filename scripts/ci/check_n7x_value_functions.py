#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
VALUES = ROOT / ".claude/value_functions/n7x_value_functions.v1.yaml"
REQUIRED_IDS = {
    "vf1_safety_as_architecture",
    "vf2_signal_over_noise",
    "vf3_judgment_over_rules",
    "vf4_understanding_before_action",
    "vf5_jaggedness_instrumentation",
    "vf6_human_oversight",
    "vf7_honest_helpfulness",
}
REQUIRED_FIELDS = {"id", "name", "principle", "operational_rule", "gate"}


def _load(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"not an object: {path}")
    return data


def validate_value_functions(path: Path = VALUES) -> dict[str, Any]:
    data = _load(path)
    values = data.get("priority_order", [])
    if not isinstance(values, list) or not values:
        raise ValueError("priority_order must be a non-empty list")
    ids = [item.get("id") for item in values if isinstance(item, dict)]
    missing = sorted(REQUIRED_IDS.difference(ids))
    extra = sorted(set(ids).difference(REQUIRED_IDS))
    if missing:
        raise ValueError(f"missing value ids: {missing}")
    if extra:
        raise ValueError(f"unknown value ids: {extra}")
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate value ids")
    for item in values:
        if not isinstance(item, dict):
            raise ValueError("each value entry must be an object")
        absent = sorted(REQUIRED_FIELDS.difference(item))
        if absent:
            raise ValueError(f"{item.get('id')} missing fields: {absent}")
        for field in REQUIRED_FIELDS:
            if not str(item[field]).strip():
                raise ValueError(f"{item['id']} has empty {field}")
    return {"status": "PASS", "id": data.get("id"), "values": len(values)}


def main() -> int:
    try:
        print(json.dumps(validate_value_functions(), sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
