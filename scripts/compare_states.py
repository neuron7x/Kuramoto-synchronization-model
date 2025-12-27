#!/usr/bin/env python
"""Utility to compare two serialized state snapshots.

The script loads two JSON files and reports any key/value differences. It exits
with code 0 when the snapshots are equivalent and 1 otherwise.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping


def _load_state(path: Path) -> Mapping[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _diff_states(left: Mapping[str, Any], right: Mapping[str, Any]) -> dict[str, Any]:
    diff: dict[str, Any] = {"only_in_left": {}, "only_in_right": {}, "mismatched": {}}
    left_keys = set(left)
    right_keys = set(right)

    for key in left_keys - right_keys:
        diff["only_in_left"][key] = left[key]
    for key in right_keys - left_keys:
        diff["only_in_right"][key] = right[key]
    for key in left_keys & right_keys:
        if left[key] != right[key]:
            diff["mismatched"][key] = {"left": left[key], "right": right[key]}
    return diff


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare two JSON-encoded state snapshots.")
    parser.add_argument("left", type=Path, help="Path to the baseline state file")
    parser.add_argument("right", type=Path, help="Path to the state file to compare against")
    args = parser.parse_args()

    left_state = _load_state(args.left)
    right_state = _load_state(args.right)
    diff = _diff_states(left_state, right_state)

    print(json.dumps(diff, indent=2, sort_keys=True))
    return 0 if not any(diff.values()) else 1


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(main())
