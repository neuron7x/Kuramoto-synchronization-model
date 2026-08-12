# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Governance — a law does not exist without a witness, a negative control, and CI.

Loads the executable falsification catalog
(``physics_contracts/falsification_catalog.yaml``) and enforces the meta-law
``law_requires_positive_and_negative_witness``: every blocking law must bind a
collected positive witness, a collected negative control, and an evidence
artifact. The promotion gate fails closed on any gap. This is SEPARATE from the
canonical 112-invariant catalog, which it never mutates.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, cast

import yaml

__all__ = [
    "REQUIRED_FIELDS",
    "DEFAULT_CATALOG_PATH",
    "load_catalog",
    "validate_law_schema",
    "check_witness_coverage",
    "check_negative_controls",
    "claim_evidence_map",
    "check_threshold_migration",
    "promotion_gate",
]

REQUIRED_FIELDS: tuple[str, ...] = (
    "id",
    "domain",
    "claim",
    "formal_invariant",
    "measured_quantity",
    "threshold",
    "positive_witness",
    "negative_control",
    "blocking",
    "failure_message",
    "evidence_output",
)

DEFAULT_CATALOG_PATH = (
    Path(__file__).resolve().parents[2] / "physics_contracts" / "falsification_catalog.yaml"
)

_NODE_ID_RE = re.compile(r"^(?P<path>tests/physics/[^:]+\.py)::(?P<name>[A-Za-z_][A-Za-z0-9_]*)$")


def load_catalog(path: str | Path | None = None) -> dict[str, Any]:
    """Parse the falsification catalog YAML into a dict with a ``laws`` list."""
    catalog_path = Path(path) if path is not None else DEFAULT_CATALOG_PATH
    with catalog_path.open(encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle)
    if not isinstance(loaded, dict) or not isinstance(loaded.get("laws"), list):
        raise ValueError(f"{catalog_path} is not a valid catalog (missing 'laws' list)")
    return cast("dict[str, Any]", loaded)


def validate_law_schema(law: dict[str, Any]) -> list[str]:
    """Return a list of schema errors for one law (empty = valid)."""
    errors: list[str] = []
    for field_name in REQUIRED_FIELDS:
        if field_name not in law:
            errors.append(f"missing required field '{field_name}'")
    if "blocking" in law and not isinstance(law["blocking"], bool):
        errors.append("field 'blocking' must be a boolean")
    for ref in ("positive_witness", "negative_control"):
        value = law.get(ref)
        if isinstance(value, str) and not _NODE_ID_RE.match(value):
            errors.append(f"'{ref}' is not a tests/physics/...::name node id: {value!r}")
    return errors


def _resolve_node(repo_root: Path, node_id: str) -> tuple[Path, str] | None:
    match = _NODE_ID_RE.match(node_id)
    if match is None:
        return None
    return repo_root / match.group("path"), match.group("name")


def _witness_collected(repo_root: Path, node_id: str) -> bool:
    resolved = _resolve_node(repo_root, node_id)
    if resolved is None:
        return False
    test_file, name = resolved
    if not test_file.is_file():
        return False
    source = test_file.read_text(encoding="utf-8")
    return bool(re.search(rf"def {re.escape(name)}\s*\(", source))


def check_witness_coverage(catalog: dict[str, Any], repo_root: str | Path) -> list[str]:
    """Return law ids whose positive witness is not a collected test function."""
    root = Path(repo_root)
    return [
        str(law.get("id"))
        for law in catalog["laws"]
        if law.get("blocking") and not _witness_collected(root, str(law.get("positive_witness")))
    ]


def check_negative_controls(catalog: dict[str, Any], repo_root: str | Path) -> list[str]:
    """Return law ids whose negative control is not a collected test function."""
    root = Path(repo_root)
    return [
        str(law.get("id"))
        for law in catalog["laws"]
        if law.get("blocking") and not _witness_collected(root, str(law.get("negative_control")))
    ]


def claim_evidence_map(catalog: dict[str, Any], repo_root: str | Path) -> dict[str, bool]:
    """Map each law id to whether its declared evidence artifact exists on disk."""
    root = Path(repo_root)
    result: dict[str, bool] = {}
    for law in catalog["laws"]:
        evidence = law.get("evidence_output")
        result[str(law.get("id"))] = bool(evidence) and (root / str(evidence)).is_file()
    return result


def check_threshold_migration(
    catalog: dict[str, Any],
    baseline: dict[str, Any],
    migration_notes: dict[str, str],
) -> list[str]:
    """Return law ids whose threshold changed vs baseline without a migration note."""
    baseline_thresholds = {
        str(law.get("id")): law.get("threshold") for law in baseline.get("laws", [])
    }
    offending: list[str] = []
    for law in catalog["laws"]:
        law_id = str(law.get("id"))
        if law_id in baseline_thresholds and law.get("threshold") != baseline_thresholds[law_id]:
            if not migration_notes.get(law_id):
                offending.append(law_id)
    return offending


def promotion_gate(
    catalog: dict[str, Any],
    repo_root: str | Path,
    *,
    require_evidence: bool = True,
) -> dict[str, Any]:
    """Aggregate the full gate verdict; status is PASS only if nothing is missing.

    ``require_evidence=False`` lets the validator run the gate BEFORE evidence is
    emitted (it then emits the artifacts); CI runs it with evidence required.
    """
    errors: list[str] = []
    for law in catalog["laws"]:
        for err in validate_law_schema(law):
            errors.append(f"{law.get('id', '?')}: {err}")

    for law_id in check_witness_coverage(catalog, repo_root):
        errors.append(f"{law_id}: blocking law has no collected positive witness")
    for law_id in check_negative_controls(catalog, repo_root):
        errors.append(f"{law_id}: blocking law has no collected negative control")

    if require_evidence:
        for law_id, present in claim_evidence_map(catalog, repo_root).items():
            if not present:
                errors.append(f"{law_id}: declared evidence artifact missing")

    return {
        "status": "PASS" if not errors else "FAIL",
        "n_laws": len(catalog["laws"]),
        "n_blocking": sum(1 for law in catalog["laws"] if law.get("blocking")),
        "errors": errors,
    }
