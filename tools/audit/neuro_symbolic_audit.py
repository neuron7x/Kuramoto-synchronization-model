# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Validator for the NEURO_OPERATIONALIZATION_LEDGER.

Audits .claude/neuro/NEURO_OPERATIONALIZATION_LEDGER.yaml for structural and
semantic correctness. Fails closed: any malformed entry exits with code 1.

Rules enforced (mirroring section 4 of the audit protocol):
  * classification ∈ {OPERATIONAL, PARTIAL, DECORATIVE, OVERCLAIM, LEGACY,
    REJECTED}.
  * remediation_action ∈ {KEEP, ADD_FALSIFIER, ADD_NULL_MODEL, ADD_TEST,
    RENAME, QUARANTINE_DOC, REJECT, DELETE}.
  * priority ∈ {P0, P1, P2, P3}.
  * runtime_path ∈ {YES, NO, UNKNOWN}.
  * id is unique and non-empty.
  * line_range is a 2-element list [start, end] with 1 ≤ start ≤ end.
  * OPERATIONAL entries must declare input_contract, output_contract,
    falsifier, at least one inv_ref, and at least one existing test.
  * PARTIAL entries must declare a remediation_action and at least one of
    {falsifier, missing_tests}.
  * DECORATIVE entries on a runtime path must declare an explicit non-claim
    in the falsifier or remediation note.
  * OVERCLAIM entries must declare a remediation action ≠ KEEP.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import yaml  # type: ignore[import-untyped]

CLASSIFICATIONS: frozenset[str] = frozenset(
    {
        "OPERATIONAL",
        "PARTIAL",
        "DECORATIVE",
        "OVERCLAIM",
        "LEGACY",
        "REJECTED",
    }
)

REMEDIATIONS: frozenset[str] = frozenset(
    {
        "KEEP",
        "ADD_FALSIFIER",
        "ADD_NULL_MODEL",
        "ADD_TEST",
        "RENAME",
        "QUARANTINE_DOC",
        "REJECT",
        "DELETE",
    }
)

PRIORITIES: frozenset[str] = frozenset({"P0", "P1", "P2", "P3"})
RUNTIME_VALUES: frozenset[str] = frozenset({"YES", "NO", "UNKNOWN"})

REQUIRED_FIELDS: tuple[str, ...] = (
    "id",
    "term",
    "file",
    "line_range",
    "current_usage",
    "classification",
    "claimed_role",
    "actual_algorithmic_role",
    "input_contract",
    "output_contract",
    "falsifier",
    "existing_tests",
    "missing_tests",
    "runtime_path",
    "remediation_action",
    "priority",
    "reason",
)

DEFAULT_LEDGER = (
    Path(__file__).resolve().parents[2]
    / ".claude"
    / "neuro"
    / "NEURO_OPERATIONALIZATION_LEDGER.yaml"
)


@dataclass(frozen=True, slots=True)
class AuditError:
    entry_id: str
    field: str
    message: str

    def render(self) -> str:
        return f"[{self.entry_id}] {self.field}: {self.message}"


def _is_nonempty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_list_of_strings(value: object) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _validate_line_range(value: object) -> str | None:
    if not isinstance(value, list) or len(value) != 2:
        return "must be a 2-element list [start, end]"
    start, end = value
    if not isinstance(start, int) or not isinstance(end, int):
        return "start and end must be integers"
    if start < 1 or end < start:
        return f"requires 1 ≤ start ≤ end (got {start}, {end})"
    return None


def _validate_required_fields(entry: Mapping[str, Any]) -> list[AuditError]:
    errors: list[AuditError] = []
    eid = str(entry.get("id", "<missing-id>"))
    for field in REQUIRED_FIELDS:
        if field not in entry:
            errors.append(AuditError(eid, field, "missing required field"))
    return errors


def _validate_enums(entry: Mapping[str, Any]) -> list[AuditError]:
    errors: list[AuditError] = []
    eid = str(entry.get("id", "<missing-id>"))

    classification = entry.get("classification")
    if classification not in CLASSIFICATIONS:
        errors.append(
            AuditError(
                eid,
                "classification",
                f"unknown classification {classification!r}; expected one of {sorted(CLASSIFICATIONS)}",
            )
        )

    remediation = entry.get("remediation_action")
    if remediation not in REMEDIATIONS:
        errors.append(
            AuditError(
                eid,
                "remediation_action",
                f"unknown remediation_action {remediation!r}; expected one of {sorted(REMEDIATIONS)}",
            )
        )

    priority = entry.get("priority")
    if priority not in PRIORITIES:
        errors.append(
            AuditError(
                eid,
                "priority",
                f"unknown priority {priority!r}; expected one of {sorted(PRIORITIES)}",
            )
        )

    runtime_path = entry.get("runtime_path")
    if runtime_path not in RUNTIME_VALUES:
        errors.append(
            AuditError(
                eid,
                "runtime_path",
                f"unknown runtime_path {runtime_path!r}; expected one of {sorted(RUNTIME_VALUES)}",
            )
        )

    return errors


def _validate_lists(entry: Mapping[str, Any]) -> list[AuditError]:
    errors: list[AuditError] = []
    eid = str(entry.get("id", "<missing-id>"))
    for field in ("existing_tests", "missing_tests"):
        if not _is_list_of_strings(entry.get(field, [])):
            errors.append(AuditError(eid, field, "must be a list of strings"))
    inv_refs = entry.get("inv_refs", [])
    if not _is_list_of_strings(inv_refs):
        errors.append(AuditError(eid, "inv_refs", "must be a list of strings"))
    return errors


def _validate_line_range_field(entry: Mapping[str, Any]) -> list[AuditError]:
    eid = str(entry.get("id", "<missing-id>"))
    msg = _validate_line_range(entry.get("line_range"))
    return [AuditError(eid, "line_range", msg)] if msg else []


def _validate_classification_specific(entry: Mapping[str, Any]) -> list[AuditError]:
    """Apply classification-specific evidence rules."""

    errors: list[AuditError] = []
    eid = str(entry.get("id", "<missing-id>"))
    classification = entry.get("classification")
    runtime_path = entry.get("runtime_path")

    falsifier = entry.get("falsifier", "")
    input_contract = entry.get("input_contract", "")
    output_contract = entry.get("output_contract", "")
    remediation = entry.get("remediation_action")
    inv_refs = entry.get("inv_refs", [])
    existing_tests = entry.get("existing_tests", [])
    missing_tests = entry.get("missing_tests", [])

    if classification == "OPERATIONAL":
        if not _is_nonempty_string(input_contract):
            errors.append(
                AuditError(eid, "input_contract", "OPERATIONAL requires non-empty input_contract")
            )
        if not _is_nonempty_string(output_contract):
            errors.append(
                AuditError(eid, "output_contract", "OPERATIONAL requires non-empty output_contract")
            )
        if not _is_nonempty_string(falsifier):
            errors.append(AuditError(eid, "falsifier", "OPERATIONAL requires non-empty falsifier"))
        if not (isinstance(inv_refs, list) and any(_is_nonempty_string(x) for x in inv_refs)):
            errors.append(
                AuditError(
                    eid,
                    "inv_refs",
                    "OPERATIONAL requires at least one INV-* reference from CLAUDE.md",
                )
            )
        if not (
            isinstance(existing_tests, list) and any(_is_nonempty_string(x) for x in existing_tests)
        ):
            errors.append(
                AuditError(
                    eid,
                    "existing_tests",
                    "OPERATIONAL requires at least one existing test path",
                )
            )

    elif classification == "PARTIAL":
        if remediation == "KEEP":
            errors.append(
                AuditError(
                    eid,
                    "remediation_action",
                    "PARTIAL must declare an active remediation (not KEEP)",
                )
            )
        if not _is_nonempty_string(falsifier) and not (
            isinstance(missing_tests, list) and any(_is_nonempty_string(x) for x in missing_tests)
        ):
            errors.append(
                AuditError(
                    eid,
                    "falsifier",
                    "PARTIAL requires either a falsifier or at least one missing_tests entry",
                )
            )

    elif classification == "DECORATIVE":
        if runtime_path == "YES":
            falsifier_text = falsifier if isinstance(falsifier, str) else ""
            reason_text = entry.get("reason", "")
            reason_text = reason_text if isinstance(reason_text, str) else ""
            if "non-claim" not in falsifier_text.lower() and "non-claim" not in reason_text.lower():
                errors.append(
                    AuditError(
                        eid,
                        "falsifier",
                        "DECORATIVE on runtime path requires explicit 'non-claim' note",
                    )
                )

    elif classification == "OVERCLAIM":
        if remediation == "KEEP":
            errors.append(
                AuditError(
                    eid,
                    "remediation_action",
                    "OVERCLAIM must not be KEEP — require active remediation",
                )
            )

    return errors


def _validate_unique_ids(entries: Sequence[Mapping[str, Any]]) -> list[AuditError]:
    errors: list[AuditError] = []
    seen: dict[str, int] = {}
    for idx, entry in enumerate(entries):
        eid = str(entry.get("id", f"<missing-id-{idx}>"))
        if not _is_nonempty_string(eid) or eid.startswith("<missing"):
            errors.append(AuditError(eid, "id", "id must be a non-empty string"))
            continue
        if eid in seen:
            errors.append(
                AuditError(
                    eid,
                    "id",
                    f"duplicate id (also at index {seen[eid]})",
                )
            )
        else:
            seen[eid] = idx
    return errors


def _validate_entry(entry: Mapping[str, Any]) -> list[AuditError]:
    errors: list[AuditError] = []
    errors.extend(_validate_required_fields(entry))
    if errors:
        return errors
    errors.extend(_validate_enums(entry))
    errors.extend(_validate_lists(entry))
    errors.extend(_validate_line_range_field(entry))
    errors.extend(_validate_classification_specific(entry))
    return errors


def validate_ledger(ledger: Mapping[str, Any]) -> list[AuditError]:
    """Return all errors found in the supplied parsed ledger document."""

    errors: list[AuditError] = []

    raw_entries = ledger.get("entries", None)
    if raw_entries is None or not isinstance(raw_entries, list):
        return [AuditError("<root>", "entries", "ledger missing 'entries' list")]

    entries = cast(list[Mapping[str, Any]], raw_entries)
    errors.extend(_validate_unique_ids(entries))
    for entry in entries:
        if not isinstance(entry, Mapping):
            errors.append(AuditError("<entry>", "type", "entry must be a mapping"))
            continue
        errors.extend(_validate_entry(entry))

    return errors


def load_ledger(path: Path) -> Mapping[str, Any]:
    """Load and parse the YAML ledger from ``path``."""

    text = path.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    if not isinstance(data, Mapping):
        raise ValueError(f"{path}: top-level YAML must be a mapping")
    return data


def render_errors(errors: Iterable[AuditError]) -> str:
    return "\n".join(error.render() for error in errors)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate NEURO_OPERATIONALIZATION_LEDGER.yaml structure",
    )
    parser.add_argument(
        "ledger",
        nargs="?",
        type=Path,
        default=DEFAULT_LEDGER,
        help="path to ledger YAML (default: %(default)s)",
    )
    args = parser.parse_args(argv)

    path: Path = args.ledger
    if not path.is_file():
        print(f"ERROR: ledger not found at {path}", file=sys.stderr)
        return 2

    try:
        ledger = load_ledger(path)
    except (yaml.YAMLError, ValueError) as exc:
        print(f"ERROR: failed to load ledger: {exc}", file=sys.stderr)
        return 2

    errors = validate_ledger(ledger)
    if errors:
        print(f"FAIL — {len(errors)} ledger error(s):", file=sys.stderr)
        print(render_errors(errors), file=sys.stderr)
        return 1

    entries = cast(list[Mapping[str, Any]], ledger.get("entries", []))
    print(f"OK — ledger valid; {len(entries)} entries audited.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
