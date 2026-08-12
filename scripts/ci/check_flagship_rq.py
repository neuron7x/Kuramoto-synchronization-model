# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Fail-closed gate over the flagship research question (RES-001).

GeoSync promotes exactly ONE research question to *flagship* status. This gate
refuses to let that question rot into an incomplete preregistration. It verifies
that the machine-readable RQ (``research/flagship/rq.yaml``) carries every
required preregistration field, that its human-readable mirror
(``research/flagship/RQ.md``) exists, and that a non-empty quarantine list of the
parked/archived parallel claims exists (``research/flagship/quarantine.yaml``).

Required RQ fields (all must be present and non-empty):

    estimand, population, intervention, comparator, outcome,
    constraints, success_criteria, failure_criteria

The gate is fail-closed: a missing field, an empty field, a missing file, or an
empty quarantine list is a hard failure. This mirrors
``scripts/ci/check_falsifier_ledger.py``.

Exit codes:
    0  — RQ complete (all fields present) and quarantine list non-empty
    1  — a required RQ field is missing/empty, or the quarantine list is empty
    2  — a required file is absent or malformed
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RQ_DIR = ROOT / "research" / "flagship"

REQUIRED_FIELDS: tuple[str, ...] = (
    "estimand",
    "population",
    "intervention",
    "comparator",
    "outcome",
    "constraints",
    "success_criteria",
    "failure_criteria",
)


class GateError(Exception):
    """Malformed / missing input — maps to exit code 2 (fail-closed)."""


def _load_yaml(path: Path) -> Any:
    if not path.exists():
        raise GateError(f"missing required file: {path}")
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:  # pragma: no cover - defensive
        raise GateError(f"malformed YAML in {path}: {exc}") from exc


def _quarantine_entries(data: Any) -> list[Any]:
    """Extract the quarantine list from a parsed quarantine.yaml.

    Accepts either a top-level list, or a mapping with a ``quarantined`` key.
    """
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("quarantined"), list):
        return data["quarantined"]
    raise GateError(
        "quarantine.yaml must be a list or a mapping with a 'quarantined' list"
    )


def evaluate(rq_dir: Path) -> dict[str, Any]:
    """Return a machine-readable verdict for the flagship RQ under *rq_dir*.

    Raises GateError (exit 2) on missing/malformed files.
    """
    rq_yaml = _load_yaml(rq_dir / "rq.yaml")
    if not isinstance(rq_yaml, dict):
        raise GateError("rq.yaml must parse to a mapping")

    rq_md = rq_dir / "RQ.md"
    if not rq_md.exists():
        raise GateError(f"missing required file: {rq_md}")
    rq_md_text = rq_md.read_text(encoding="utf-8")

    missing_fields: list[str] = []
    md_missing_labels: list[str] = []
    for field in REQUIRED_FIELDS:
        value = rq_yaml.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            missing_fields.append(field)
        # The human-readable mirror must also name every required field.
        if field not in rq_md_text:
            md_missing_labels.append(field)

    quarantine = _quarantine_entries(_load_yaml(rq_dir / "quarantine.yaml"))

    problems: list[str] = []
    for field in missing_fields:
        problems.append(f"rq.yaml: required field '{field}' missing or empty")
    for field in md_missing_labels:
        problems.append(f"RQ.md: required field '{field}' not documented")
    if len(quarantine) == 0:
        problems.append("quarantine.yaml: quarantine list is empty")

    return {
        "rq_dir": str(rq_dir),
        "flagship_id": rq_yaml.get("id"),
        "required_fields": list(REQUIRED_FIELDS),
        "missing_fields": missing_fields,
        "md_missing_labels": md_missing_labels,
        "quarantine_count": len(quarantine),
        "problems": problems,
        "ok": not problems,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--rq-dir",
        type=Path,
        default=DEFAULT_RQ_DIR,
        help="directory holding rq.yaml / RQ.md / quarantine.yaml",
    )
    parser.add_argument(
        "--json", action="store_true", help="emit machine-readable verdict"
    )
    args = parser.parse_args(argv)

    try:
        verdict = evaluate(args.rq_dir)
    except GateError as exc:
        if args.json:
            print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        else:
            print(f"FLAGSHIP-RQ GATE: MALFORMED — {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(verdict, indent=2))
    else:
        if verdict["ok"]:
            print(
                f"FLAGSHIP-RQ GATE: PASS — {verdict['flagship_id']} complete; "
                f"{verdict['quarantine_count']} claim(s) quarantined."
            )
        else:
            print("FLAGSHIP-RQ GATE: FAIL", file=sys.stderr)
            for problem in verdict["problems"]:
                print(f"  - {problem}", file=sys.stderr)

    return 0 if verdict["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
