# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Validator for the OLD_REPO_SALVAGE_LEDGER.

Checks the salvage ledger that maps every artifact in the old
Kuramoto/TradePulse repository to its current state in GeoSync. Fail-closed:
malformed entries exit with code 1.

Rules enforced:
  * status ∈ {PRESENT_IN_NEW, MISSING, PARTIAL, RENAMED, OBSOLETE,
    OVERCLAIM, UNKNOWN}.
  * artifact_type ∈ {CODE, TEST, DOC, CONFIG, IP, PRODUCT, CLI, WORKFLOW}.
  * importance ∈ {CRITICAL, HIGH, MEDIUM, LOW}.
  * uniqueness ∈ {UNIQUE, COMMON, DERIVATIVE, UNKNOWN}.
  * migration_action ∈ {PORT, PORT_TESTS_ONLY, ARCHIVE, QUARANTINE,
    REWRITE, REJECT, KEEP_NEW}.
  * id is unique and non-empty; old_path is non-empty.
  * CRITICAL or HIGH entries must declare a migration_action.
  * CODE entries with PORT must declare at least one required_tests entry.
  * IP entries must use ARCHIVE or QUARANTINE.
  * OVERCLAIM status entries must declare required_non_claim.
  * PRODUCT entries must declare a non-empty owner_surface.
  * TEST entries must declare a non-empty owner_surface.
  * MISSING entries must declare a migration_action (any non-empty value).
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import yaml  # type: ignore[import-untyped,unused-ignore]

STATUSES: frozenset[str] = frozenset(
    {
        "PRESENT_IN_NEW",
        "MISSING",
        "PARTIAL",
        "RENAMED",
        "OBSOLETE",
        "OVERCLAIM",
        "UNKNOWN",
    }
)

ARTIFACT_TYPES: frozenset[str] = frozenset(
    {"CODE", "TEST", "DOC", "CONFIG", "IP", "PRODUCT", "CLI", "WORKFLOW"}
)

IMPORTANCES: frozenset[str] = frozenset({"CRITICAL", "HIGH", "MEDIUM", "LOW"})
UNIQUENESS: frozenset[str] = frozenset({"UNIQUE", "COMMON", "DERIVATIVE", "UNKNOWN"})

MIGRATION_ACTIONS: frozenset[str] = frozenset(
    {
        "PORT",
        "PORT_TESTS_ONLY",
        "ARCHIVE",
        "QUARANTINE",
        "REWRITE",
        "REJECT",
        "KEEP_NEW",
    }
)

REQUIRED_FIELDS: tuple[str, ...] = (
    "id",
    "old_path",
    "new_path_candidate",
    "artifact_type",
    "status",
    "importance",
    "uniqueness",
    "mechanism_summary",
    "what_is_real",
    "what_is_overclaim",
    "migration_action",
    "required_non_claim",
    "required_tests",
    "falsifier",
    "owner_surface",
    "reason",
)

DEFAULT_LEDGER = (
    Path(__file__).resolve().parents[2] / ".claude" / "archive" / "OLD_REPO_SALVAGE_LEDGER.yaml"
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

    pairs: tuple[tuple[str, frozenset[str]], ...] = (
        ("status", STATUSES),
        ("artifact_type", ARTIFACT_TYPES),
        ("importance", IMPORTANCES),
        ("uniqueness", UNIQUENESS),
        ("migration_action", MIGRATION_ACTIONS),
    )
    for field, valid in pairs:
        if entry.get(field) not in valid:
            errors.append(
                AuditError(
                    eid,
                    field,
                    f"unknown {field}={entry.get(field)!r}; expected one of {sorted(valid)}",
                )
            )
    return errors


def _validate_lists(entry: Mapping[str, Any]) -> list[AuditError]:
    errors: list[AuditError] = []
    eid = str(entry.get("id", "<missing-id>"))
    if not _is_list_of_strings(entry.get("required_tests", [])):
        errors.append(AuditError(eid, "required_tests", "must be a list of strings"))
    return errors


def _validate_old_path(entry: Mapping[str, Any]) -> list[AuditError]:
    eid = str(entry.get("id", "<missing-id>"))
    if not _is_nonempty_string(entry.get("old_path", "")):
        return [AuditError(eid, "old_path", "old_path must be a non-empty string")]
    return []


def _validate_classification_specific(entry: Mapping[str, Any]) -> list[AuditError]:
    errors: list[AuditError] = []
    eid = str(entry.get("id", "<missing-id>"))
    importance = entry.get("importance")
    artifact_type = entry.get("artifact_type")
    status = entry.get("status")
    migration = entry.get("migration_action", "")
    required_non_claim = entry.get("required_non_claim", "")
    required_tests = entry.get("required_tests", [])
    owner_surface = entry.get("owner_surface", "")

    if importance in {"CRITICAL", "HIGH"} and migration not in MIGRATION_ACTIONS:
        errors.append(
            AuditError(
                eid,
                "migration_action",
                "CRITICAL/HIGH entry requires a declared migration_action",
            )
        )

    if artifact_type == "CODE" and migration == "PORT":
        if not (
            isinstance(required_tests, list) and any(_is_nonempty_string(t) for t in required_tests)
        ):
            errors.append(
                AuditError(
                    eid,
                    "required_tests",
                    "CODE with PORT requires at least one required_tests entry",
                )
            )

    if artifact_type == "IP" and migration not in {"ARCHIVE", "QUARANTINE"}:
        errors.append(
            AuditError(
                eid,
                "migration_action",
                "IP artefact must use ARCHIVE or QUARANTINE",
            )
        )

    if status == "OVERCLAIM" and not _is_nonempty_string(required_non_claim):
        errors.append(
            AuditError(
                eid,
                "required_non_claim",
                "OVERCLAIM entry requires a non-empty required_non_claim",
            )
        )

    if artifact_type == "PRODUCT" and not _is_nonempty_string(owner_surface):
        errors.append(
            AuditError(
                eid,
                "owner_surface",
                "PRODUCT entry requires a non-empty owner_surface (buyer / use-case)",
            )
        )

    if artifact_type == "TEST" and not _is_nonempty_string(owner_surface):
        errors.append(
            AuditError(
                eid,
                "owner_surface",
                "TEST entry requires a non-empty owner_surface (linked module / reason)",
            )
        )

    if status == "MISSING" and not _is_nonempty_string(migration):
        errors.append(
            AuditError(
                eid,
                "migration_action",
                "MISSING entry requires a declared migration_action",
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
    errors.extend(_validate_old_path(entry))
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
    text = path.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    if not isinstance(data, Mapping):
        raise ValueError(f"{path}: top-level YAML must be a mapping")
    return data


def render_errors(errors: Iterable[AuditError]) -> str:
    return "\n".join(error.render() for error in errors)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate OLD_REPO_SALVAGE_LEDGER.yaml structure",
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
    print(f"OK — salvage ledger valid; {len(entries)} entries audited.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
