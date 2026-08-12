#!/usr/bin/env python3
# SPDX-License-Identifier: MIT

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "autonomy_trend.v1"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _read_ledger(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": SCHEMA_VERSION, "entries": [], "summary": _summary([])}
    ledger = _read_object(path)
    if ledger.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("ledger schema_version mismatch")
    entries = ledger.get("entries")
    if not isinstance(entries, list):
        raise ValueError("ledger entries must be a list")
    return ledger


def _status_vector(phases: Any) -> list[str]:
    if not isinstance(phases, list):
        raise ValueError("cycle phases must be a list")
    return [str(item.get("status", "UNKNOWN")) for item in phases if isinstance(item, dict)]


def _entry(cycle_path: Path, cycle: dict[str, Any], sequence: int) -> dict[str, Any]:
    decision = cycle.get("decision")
    phases = cycle.get("phases")
    if not isinstance(decision, dict):
        raise ValueError("cycle decision must be an object")
    vector = _status_vector(phases)
    return {
        "sequence": sequence,
        "cycle_schema_version": str(cycle.get("schema_version", "")),
        "cycle_sha256": _sha256(cycle_path),
        "decision_state": str(decision.get("state", "UNKNOWN")),
        "status_vector": vector,
        "status_counts": dict(sorted(Counter(vector).items())),
        "phase_count": len(phases),
    }


def _summary(entries: list[dict[str, Any]]) -> dict[str, Any]:
    decision_counts = Counter(
        str(item.get("decision_state", "UNKNOWN")) for item in entries if isinstance(item, dict)
    )
    status_counts: Counter[str] = Counter()
    phase_count_total = 0
    for item in entries:
        if not isinstance(item, dict):
            continue
        counts = item.get("status_counts")
        if isinstance(counts, dict):
            status_counts.update(
                {str(key): int(value) for key, value in counts.items() if isinstance(value, int)}
            )
        phase_count = item.get("phase_count")
        if isinstance(phase_count, int) and not isinstance(phase_count, bool):
            phase_count_total += phase_count
    latest = entries[-1] if entries else None
    return {
        "total_cycles": len(entries),
        "decision_counts": dict(sorted(decision_counts.items())),
        "status_counts": dict(sorted(status_counts.items())),
        "phase_count_total": phase_count_total,
        "latest_decision_state": None if latest is None else latest.get("decision_state"),
        "latest_cycle_sha256": None if latest is None else latest.get("cycle_sha256"),
    }


def _next_sequence(entries: list[dict[str, Any]]) -> int:
    values = [item.get("sequence") for item in entries if isinstance(item, dict)]
    numeric = [value for value in values if isinstance(value, int) and not isinstance(value, bool)]
    return (max(numeric) if numeric else 0) + 1


def _rooted(root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def build_ledger(cycle_path: Path, ledger_path: Path, limit: int) -> dict[str, Any]:
    if limit <= 0:
        raise ValueError("limit must be positive")
    cycle = _read_object(cycle_path)
    ledger = _read_ledger(ledger_path)
    entries = list(ledger["entries"])
    entries.append(_entry(cycle_path, cycle, _next_sequence(entries)))
    entries = entries[-limit:]
    return {"schema_version": SCHEMA_VERSION, "entries": entries, "summary": _summary(entries)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--cycle", default="artifacts/validation/autonomy_cycle.json")
    parser.add_argument("--ledger", default="artifacts/validation/autonomy_trend.json")
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    cycle_path = _rooted(root, args.cycle)
    ledger_path = _rooted(root, args.ledger)
    payload = build_ledger(cycle_path, ledger_path, args.limit)
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
