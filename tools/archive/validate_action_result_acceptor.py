# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Validator for the ACTION_RESULT_ACCEPTOR_LEDGER.

Enforces the law: no action without an acceptor.
Every OPERATIONAL entry must declare the full chain
  action → expected → observed → error → update / rollback → falsifier → tests.

Fail-closed: any malformed entry causes exit 1.
Emits a deterministic JSON summary to ``tmp/action_result_acceptor_validation.json``
(parent dir created on demand).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import yaml  # type: ignore[import-untyped,unused-ignore]

MECHANISM_TYPES: frozenset[str] = frozenset(
    {
        "PROMPT_OUTCOME_ACCEPTOR",
        "CONSENSUS_FEEDBACK_ACCEPTOR",
        "STRATEGY_MEMORY_ACCEPTOR",
        "EXECUTION_RESULT_ACCEPTOR",
        "RISK_GUARDIAN_ACCEPTOR",
        "CLAIM_RESULT_ACCEPTOR",
        "MISSING_CONCEPT",
        "DECORATIVE_LABEL",
    }
)

STATUSES: frozenset[str] = frozenset(
    {
        "OPERATIONAL",
        "PARTIAL",
        "MISSING_IN_NEW",
        "PRESENT_IN_NEW",
        "RENAMED_IN_NEW",
        "DECORATIVE",
        "OVERCLAIM",
        "REJECTED",
        "UNKNOWN",
    }
)

IMPORTANCES: frozenset[str] = frozenset({"CRITICAL", "HIGH", "MEDIUM", "LOW"})

MIGRATION_ACTIONS: frozenset[str] = frozenset(
    {
        "KEEP_NEW",
        "PORT",
        "PORT_TESTS_ONLY",
        "REWRITE",
        "ARCHIVE",
        "QUARANTINE",
        "REJECT",
        "INVESTIGATE",
    }
)

REQUIRED_FIELDS: tuple[str, ...] = (
    "id",
    "old_path",
    "new_path",
    "mechanism_type",
    "status",
    "importance",
    "action_source",
    "expected_result",
    "observed_result",
    "error_signal",
    "update_rule",
    "rollback_rule",
    "memory_effect",
    "existing_tests",
    "missing_tests",
    "falsifier",
    "migration_action",
    "reason",
)

DEFAULT_LEDGER = (
    Path(__file__).resolve().parents[2]
    / ".claude"
    / "archive"
    / "ACTION_RESULT_ACCEPTOR_LEDGER.yaml"
)

DEFAULT_OUTPUT = (
    Path(__file__).resolve().parents[2] / "tmp" / "action_result_acceptor_validation.json"
)


@dataclass(frozen=True, slots=True)
class AuditError:
    entry_id: str
    rule: str
    field: str
    message: str

    def render(self) -> str:
        return f"[{self.entry_id}] {self.rule}/{self.field}: {self.message}"

    def to_dict(self) -> dict[str, str]:
        return {
            "entry_id": self.entry_id,
            "rule": self.rule,
            "field": self.field,
            "message": self.message,
        }


def _is_nonempty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_list_of_strings(value: object) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _validate_required_fields(entry: Mapping[str, Any]) -> list[AuditError]:
    eid = str(entry.get("id", "<missing-id>"))
    return [
        AuditError(eid, "MISSING_FIELD", field, "missing required field")
        for field in REQUIRED_FIELDS
        if field not in entry
    ]


def _validate_enums(entry: Mapping[str, Any]) -> list[AuditError]:
    eid = str(entry.get("id", "<missing-id>"))
    errors: list[AuditError] = []

    pairs: tuple[tuple[str, frozenset[str], str], ...] = (
        ("mechanism_type", MECHANISM_TYPES, "UNKNOWN_MECHANISM_TYPE"),
        ("status", STATUSES, "UNKNOWN_STATUS"),
        ("importance", IMPORTANCES, "UNKNOWN_IMPORTANCE"),
        ("migration_action", MIGRATION_ACTIONS, "UNKNOWN_MIGRATION_ACTION"),
    )
    for field, valid, rule in pairs:
        if entry.get(field) not in valid:
            errors.append(
                AuditError(
                    eid,
                    rule,
                    field,
                    f"unknown {field}={entry.get(field)!r}; expected one of {sorted(valid)}",
                )
            )
    return errors


def _validate_lists(entry: Mapping[str, Any]) -> list[AuditError]:
    eid = str(entry.get("id", "<missing-id>"))
    errors: list[AuditError] = []
    for field in ("existing_tests", "missing_tests"):
        if not _is_list_of_strings(entry.get(field, [])):
            errors.append(AuditError(eid, "INVALID_LIST", field, "must be a list of strings"))
    return errors


def _validate_acceptor_chain(entry: Mapping[str, Any]) -> list[AuditError]:
    """Apply status-specific evidence rules — the heart of the acceptor law."""

    errors: list[AuditError] = []
    eid = str(entry.get("id", "<missing-id>"))
    status = entry.get("status")
    mech = entry.get("mechanism_type")
    importance = entry.get("importance")
    action_source = entry.get("action_source", "")
    observed_result = entry.get("observed_result", "")
    error_signal = entry.get("error_signal", "")
    update_rule = entry.get("update_rule", "")
    rollback_rule = entry.get("rollback_rule", "")
    falsifier = entry.get("falsifier", "")
    existing_tests = entry.get("existing_tests", [])
    missing_tests = entry.get("missing_tests", [])
    migration = entry.get("migration_action")
    new_path = entry.get("new_path", "")
    old_path = entry.get("old_path", "")
    reason = entry.get("reason", "")

    if status == "OPERATIONAL":
        if not _is_nonempty_string(action_source):
            errors.append(
                AuditError(
                    eid,
                    "OPERATIONAL_NO_ACTION",
                    "action_source",
                    "OPERATIONAL requires action_source",
                )
            )
        if not _is_nonempty_string(observed_result):
            errors.append(
                AuditError(
                    eid,
                    "OPERATIONAL_NO_OBSERVED",
                    "observed_result",
                    "OPERATIONAL requires observed_result",
                )
            )
        if not _is_nonempty_string(error_signal):
            errors.append(
                AuditError(
                    eid,
                    "OPERATIONAL_NO_ERROR",
                    "error_signal",
                    "OPERATIONAL requires error_signal",
                )
            )
        if not (_is_nonempty_string(update_rule) or _is_nonempty_string(rollback_rule)):
            errors.append(
                AuditError(
                    eid,
                    "OPERATIONAL_NO_UPDATE_OR_ROLLBACK",
                    "update_rule|rollback_rule",
                    "OPERATIONAL requires either update_rule or rollback_rule",
                )
            )
        if not _is_nonempty_string(falsifier):
            errors.append(
                AuditError(
                    eid, "OPERATIONAL_NO_FALSIFIER", "falsifier", "OPERATIONAL requires falsifier"
                )
            )
        if not (
            isinstance(existing_tests, list) and any(_is_nonempty_string(t) for t in existing_tests)
        ):
            errors.append(
                AuditError(
                    eid,
                    "OPERATIONAL_NO_TESTS",
                    "existing_tests",
                    "OPERATIONAL requires at least one existing test path",
                )
            )

    if status == "PARTIAL" and migration == "KEEP_NEW":
        errors.append(
            AuditError(
                eid,
                "PARTIAL_KEEP_NEW_FORBIDDEN",
                "migration_action",
                "PARTIAL must declare an active remediation, not KEEP_NEW",
            )
        )

    if status == "DECORATIVE" and migration == "PORT":
        errors.append(
            AuditError(
                eid,
                "DECORATIVE_PORT_FORBIDDEN",
                "migration_action",
                "DECORATIVE entry cannot use PORT — naming only",
            )
        )

    if status == "OVERCLAIM" and migration not in {"QUARANTINE", "REWRITE", "REJECT"}:
        errors.append(
            AuditError(
                eid,
                "OVERCLAIM_REQUIRES_REMEDIATION",
                "migration_action",
                "OVERCLAIM requires QUARANTINE, REWRITE or REJECT",
            )
        )

    if status == "MISSING_IN_NEW" and migration not in MIGRATION_ACTIONS:
        errors.append(
            AuditError(
                eid,
                "MISSING_IN_NEW_NO_ACTION",
                "migration_action",
                "MISSING_IN_NEW requires a declared migration_action",
            )
        )

    if migration == "PORT" and not (
        isinstance(missing_tests, list) and any(_is_nonempty_string(t) for t in missing_tests)
    ):
        errors.append(
            AuditError(
                eid,
                "PORT_NO_TEST_PATH",
                "missing_tests",
                "PORT must declare at least one missing_tests entry as the migration target",
            )
        )

    if migration == "PORT_TESTS_ONLY" and not _is_nonempty_string(new_path):
        errors.append(
            AuditError(
                eid,
                "PORT_TESTS_NO_NEW_PATH",
                "new_path",
                "PORT_TESTS_ONLY requires a candidate new_path to host the ported tests",
            )
        )

    if migration == "ARCHIVE" and not _is_nonempty_string(old_path):
        errors.append(
            AuditError(
                eid,
                "ARCHIVE_NO_SOURCE",
                "old_path",
                "ARCHIVE requires a source old_path (the artefact to archive)",
            )
        )

    if migration == "REJECT" and not _is_nonempty_string(reason):
        errors.append(
            AuditError(eid, "REJECT_NO_REASON", "reason", "REJECT requires an explicit reason")
        )

    if importance in {"CRITICAL", "HIGH"} and not _is_nonempty_string(reason):
        errors.append(
            AuditError(
                eid,
                "CRITICAL_NO_REASON",
                "reason",
                "CRITICAL/HIGH entry requires a non-empty reason",
            )
        )

    # Mechanism cross-check: OPERATIONAL entries should have a real mechanism_type.
    if status == "OPERATIONAL" and mech in {"DECORATIVE_LABEL", "MISSING_CONCEPT"}:
        errors.append(
            AuditError(
                eid,
                "OPERATIONAL_DECORATIVE_MISMATCH",
                "mechanism_type",
                f"OPERATIONAL is incompatible with mechanism_type={mech}",
            )
        )

    return errors


def _validate_unique_ids(entries: Sequence[Mapping[str, Any]]) -> list[AuditError]:
    errors: list[AuditError] = []
    seen: dict[str, int] = {}
    for idx, entry in enumerate(entries):
        eid = str(entry.get("id", f"<missing-id-{idx}>"))
        if not _is_nonempty_string(eid) or eid.startswith("<missing"):
            errors.append(AuditError(eid, "INVALID_ID", "id", "id must be a non-empty string"))
            continue
        if eid in seen:
            errors.append(
                AuditError(eid, "DUPLICATE_ID", "id", f"duplicate id (also at index {seen[eid]})")
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
    errors.extend(_validate_acceptor_chain(entry))
    return errors


def validate_ledger(ledger: Mapping[str, Any]) -> list[AuditError]:
    """Return all errors found in the supplied parsed ledger document."""

    errors: list[AuditError] = []
    raw_entries = ledger.get("entries", None)
    if raw_entries is None or not isinstance(raw_entries, list):
        return [AuditError("<root>", "MISSING_ENTRIES", "entries", "ledger missing 'entries' list")]

    entries = cast(list[Mapping[str, Any]], raw_entries)
    errors.extend(_validate_unique_ids(entries))
    for entry in entries:
        if not isinstance(entry, Mapping):
            errors.append(AuditError("<entry>", "INVALID_ENTRY", "type", "entry must be a mapping"))
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


def build_summary(
    ledger: Mapping[str, Any],
    errors: Sequence[AuditError],
) -> dict[str, Any]:
    """Deterministic JSON-friendly summary."""

    entries = cast(list[Mapping[str, Any]], ledger.get("entries", []))

    def count_where(predicate: Any) -> int:
        return sum(1 for e in entries if isinstance(e, Mapping) and predicate(e))

    return {
        "valid": not errors,
        "entry_count": len(entries),
        "errors": [e.to_dict() for e in errors],
        "warnings": [],
        "critical_count": count_where(lambda e: e.get("importance") == "CRITICAL"),
        "high_count": count_where(lambda e: e.get("importance") == "HIGH"),
        "missing_in_new_count": count_where(lambda e: e.get("status") == "MISSING_IN_NEW"),
        "port_count": count_where(lambda e: e.get("migration_action") == "PORT"),
        "rewrite_count": count_where(lambda e: e.get("migration_action") == "REWRITE"),
        "archive_count": count_where(lambda e: e.get("migration_action") == "ARCHIVE"),
        "reject_count": count_where(lambda e: e.get("migration_action") == "REJECT"),
    }


def write_summary(path: Path, summary: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    path.write_text(payload, encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate ACTION_RESULT_ACCEPTOR_LEDGER.yaml structure",
    )
    parser.add_argument(
        "ledger",
        nargs="?",
        type=Path,
        default=DEFAULT_LEDGER,
        help="path to ledger YAML (default: %(default)s)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="destination of the deterministic JSON summary",
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
    summary = build_summary(ledger, errors)
    write_summary(args.output, summary)

    if errors:
        print(f"FAIL — {len(errors)} ledger error(s):", file=sys.stderr)
        print(render_errors(errors), file=sys.stderr)
        return 1

    print(f"OK — acceptor ledger valid; {summary['entry_count']} entries audited.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
