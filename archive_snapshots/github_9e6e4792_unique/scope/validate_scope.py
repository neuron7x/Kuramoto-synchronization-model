#!/usr/bin/env python3
"""Validation script for RLHF/RLAIF scope artefacts."""
from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Set

ROOT = Path(__file__).resolve().parents[1]
DOC_PATH = ROOT / "docs" / "rlhf_rlaif_strategy.md"
WBS_PATH = ROOT / "scope" / "wbs.json"
DELIV_PATH = ROOT / "scope" / "deliverables.csv"

LINE_PATTERN = re.compile(r"^§([0-9]+(?:\.[0-9]+)?)?:L(\d+)(?:-L(\d+))?$")
DEL_PATTERN = re.compile(r"^DEL-\d{3}$")


def load_wbs() -> Dict[str, Dict[str, Any]]:
    with WBS_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)
    nodes: Dict[str, Dict[str, Any]] = {}

    def walk(node: Dict[str, Any]) -> None:
        code = node["code"]
        if code in nodes:
            raise ValueError(f"Duplicate WBS code detected: {code}")
        nodes[code] = node
        if "owner" not in node or not str(node["owner"]).strip():
            raise ValueError(f"Owner missing for {code}")
        children = node.get("children") or []
        if children:
            for child in children:
                walk(child)
        else:
            duration = node.get("duration_weeks")
            if duration is None:
                raise ValueError(f"Leaf task {code} missing duration")
            if duration <= 0 or duration > 1:
                raise ValueError(
                    f"Leaf task {code} has invalid duration {duration}; expected 0<duration<=1"
                )
            if not node.get("deliverables"):
                raise ValueError(f"Leaf task {code} missing deliverables")
            if not node.get("test_refs"):
                raise ValueError(f"Leaf task {code} missing test references")

    for top in data.get("wbs", []):
        walk(top)
    return nodes


def load_deliverables() -> List[Dict[str, str]]:
    with DELIV_PATH.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    required = {
        "DEL",
        "Description",
        "Definition_of_Done",
        "Dependencies",
        "WBS_Refs",
        "Source",
    }
    missing_cols = required - set(rows[0].keys()) if rows else required
    if missing_cols:
        raise ValueError(f"Deliverables CSV missing columns: {sorted(missing_cols)}")
    return rows


def validate_sources(rows: Iterable[Dict[str, str]], max_line: int) -> None:
    for row in rows:
        source = row["Source"].strip()
        match = LINE_PATTERN.match(source)
        if not match:
            raise ValueError(f"Invalid source format for {row['DEL']}: {source}")
        start_line = int(match.group(2))
        end_line = int(match.group(3) or start_line)
        if start_line < 1 or end_line < start_line or end_line > max_line:
            raise ValueError(f"Line range out of bounds for {row['DEL']}: {source}")


def main() -> int:
    if not DOC_PATH.exists():
        raise FileNotFoundError(f"Source document not found: {DOC_PATH}")
    with DOC_PATH.open("r", encoding="utf-8") as f:
        doc_lines = f.readlines()
    max_line = len(doc_lines)

    wbs_nodes = load_wbs()
    all_wbs_codes: Set[str] = set(wbs_nodes.keys())
    leaves_with_deliverables: Dict[str, Set[str]] = {}
    for code, node in wbs_nodes.items():
        children = node.get("children") or []
        if not children:
            leaves_with_deliverables[code] = set(node.get("deliverables", []))

    rows = load_deliverables()
    if not rows:
        raise ValueError("Deliverables CSV is empty")

    ids_seen: Set[str] = set()
    deliverable_to_wbs: Dict[str, Set[str]] = {}
    for row in rows:
        del_id = row["DEL"].strip()
        if not DEL_PATTERN.match(del_id):
            raise ValueError(f"Invalid deliverable ID format: {del_id}")
        if del_id in ids_seen:
            raise ValueError(f"Duplicate deliverable ID: {del_id}")
        ids_seen.add(del_id)

        description = row["Description"].strip()
        if not description:
            raise ValueError(f"Empty description for {del_id}")
        dod = row["Definition_of_Done"].strip()
        if not dod:
            raise ValueError(f"Empty Definition of Done for {del_id}")

        deps = {d.strip() for d in row["Dependencies"].split(";") if d.strip()}
        for dep in deps:
            if not DEL_PATTERN.match(dep):
                raise ValueError(f"Invalid dependency '{dep}' on {del_id}")
        deliverable_to_wbs[del_id] = set()
        wbs_refs = {w.strip() for w in row["WBS_Refs"].split(";") if w.strip()}
        if not wbs_refs:
            raise ValueError(f"No WBS references for {del_id}")
        for ref in wbs_refs:
            if ref not in all_wbs_codes:
                raise ValueError(f"Unknown WBS reference '{ref}' in {del_id}")
            deliverable_to_wbs[del_id].add(ref)
        validate_sources([row], max_line)

    # Ensure deliverables referenced from WBS exist in CSV
    wbs_deliverables = {
        deliv for dels in leaves_with_deliverables.values() for deliv in dels
    }
    missing = wbs_deliverables - set(deliverable_to_wbs.keys())
    if missing:
        raise ValueError(
            f"Deliverables referenced in WBS but missing from CSV: {sorted(missing)}"
        )

    # Ensure no orphan deliverables (each referenced by at least one WBS leaf)
    for del_id, refs in deliverable_to_wbs.items():
        if not refs & set(leaves_with_deliverables.keys()):
            raise ValueError(f"Deliverable {del_id} is not linked to any leaf WBS task")

    # Ensure WBS leaves mention deliverables that exist
    for code, delivs in leaves_with_deliverables.items():
        for deliv in delivs:
            if deliv not in deliverable_to_wbs:
                raise ValueError(f"Leaf {code} references unknown deliverable {deliv}")

    print("Scope validation passed: WBS structure and deliverables are consistent.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
