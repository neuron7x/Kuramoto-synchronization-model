#!/usr/bin/env python3
"""Validation script for RLHF/RLAIF scope artifacts."""
from __future__ import annotations

import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WBS_PATH = ROOT / "wbs.json"
DELIVERABLES_PATH = ROOT / "deliverables.csv"

SOURCE_PATTERN = re.compile(r"^\d+(?:\.\d+)*:(?:\d+)(?:-\d+)?$")
WBS_ID_PATTERN = re.compile(r"^WBS-\d+(?:\.\d+)*$")
DEL_ID_PATTERN = re.compile(r"^DEL-\d{3}$")


def load_wbs(node: dict, parent: str | None = None, mapping: dict[str, dict] | None = None) -> dict[str, dict]:
    if mapping is None:
        mapping = {}
    node_id = node.get("id")
    if not node_id or not WBS_ID_PATTERN.match(node_id):
        raise ValueError(f"Invalid or missing WBS id: {node_id!r}")
    node_copy = dict(node)
    node_copy["parent"] = parent
    mapping[node_id] = node_copy
    for child in node.get("children", []) or []:
        load_wbs(child, node_id, mapping)
    return mapping


def collect_leaves(wbs_map: dict[str, dict]) -> list[dict]:
    leaves = []
    for node in wbs_map.values():
        children = node.get("children")
        if not children:
            leaves.append(node)
    return leaves


def parse_deliverables() -> list[dict]:
    with DELIVERABLES_PATH.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    if not rows:
        raise ValueError("Deliverables CSV is empty")
    return rows


def validate_sources(source_field: str, del_id: str) -> None:
    for raw in filter(None, (part.strip() for part in source_field.split(";"))):
        if not SOURCE_PATTERN.match(raw):
            raise ValueError(f"Deliverable {del_id} has invalid source reference: {raw}")


def main() -> int:
    if not WBS_PATH.exists():
        raise FileNotFoundError(f"Missing WBS file: {WBS_PATH}")
    if not DELIVERABLES_PATH.exists():
        raise FileNotFoundError(f"Missing deliverables file: {DELIVERABLES_PATH}")

    wbs_data = json.loads(WBS_PATH.read_text(encoding="utf-8"))
    wbs_map = load_wbs(wbs_data)
    leaves = collect_leaves(wbs_map)

    # Validate leaves
    for leaf in leaves:
        leaf_id = leaf["id"]
        owner = leaf.get("owner", "").strip()
        if not owner:
            raise ValueError(f"Leaf {leaf_id} is missing owner")
        duration = leaf.get("duration_weeks")
        if duration is None:
            raise ValueError(f"Leaf {leaf_id} missing duration")
        if duration > 1:
            raise ValueError(f"Leaf {leaf_id} exceeds 1 week duration ({duration})")
        deliverables = leaf.get("deliverables", [])
        if not deliverables:
            raise ValueError(f"Leaf {leaf_id} lacks deliverable linkage")
        for del_id in deliverables:
            if not DEL_ID_PATTERN.match(del_id):
                raise ValueError(f"Leaf {leaf_id} references malformed deliverable id {del_id}")

    # Parent deliverable references should exist in CSV
    del_rows = parse_deliverables()
    deliverable_ids = set()
    wbs_to_del = defaultdict(set)
    for row in del_rows:
        del_id = row.get("DEL", "").strip()
        if not DEL_ID_PATTERN.match(del_id):
            raise ValueError(f"Invalid deliverable id: {del_id}")
        deliverable_ids.add(del_id)
        validate_sources(row.get("Source", ""), del_id)
        wbs_refs = [part.strip() for part in row.get("WBS_References", "").split(";") if part.strip()]
        if not wbs_refs:
            raise ValueError(f"Deliverable {del_id} lacks WBS references")
        for ref in wbs_refs:
            if ref not in wbs_map:
                raise ValueError(f"Deliverable {del_id} references unknown WBS id {ref}")
            wbs_to_del[ref].add(del_id)
        test_refs = [part.strip() for part in row.get("TestReferences", "").split(";") if part.strip()]
        if not test_refs:
            raise ValueError(f"Deliverable {del_id} missing test references")
        for test_ref in test_refs:
            if " " in test_ref:
                raise ValueError(f"Deliverable {del_id} test reference contains whitespace: {test_ref}")

    # Ensure WBS deliverable references exist
    for node_id, node in wbs_map.items():
        for del_id in node.get("deliverables", []) or []:
            if del_id not in deliverable_ids:
                raise ValueError(f"WBS node {node_id} references unknown deliverable {del_id}")

    # Detect orphan deliverables (not linked by any WBS)
    orphaned = sorted(deliverable_ids - set().union(*wbs_to_del.values())) if wbs_to_del else []
    if orphaned:
        raise ValueError(f"Deliverables without WBS linkage: {', '.join(orphaned)}")

    # Ensure each leaf's deliverables appear in CSV mapping
    for leaf in leaves:
        leaf_id = leaf["id"]
        if leaf_id not in wbs_to_del:
            raise ValueError(f"Leaf {leaf_id} has no deliverables mapped in CSV")

    print("Validation successful: WBS and deliverables are consistent.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
