"""Data validation primitives executed after migrations."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import sqlalchemy as sa
import yaml


@dataclass(slots=True)
class ValidationCheck:
    """Declarative expectation applied to query results."""

    kind: str
    threshold: float | int | None = None
    equals: Any | None = None
    allowed_values: Sequence[Any] | None = None
    column: str | None = None


@dataclass(slots=True)
class ValidationRule:
    """A single validation comprised of a SQL query and expectations."""

    name: str
    query: str
    params: Mapping[str, Any]
    checks: tuple[ValidationCheck, ...]


@dataclass(slots=True)
class ValidationResult:
    """Result of executing a validation rule."""

    name: str
    succeeded: bool
    details: Mapping[str, Any]
    executed_at: dt.datetime


@dataclass(slots=True)
class ValidationSuite:
    """Collection of validation rules evaluated sequentially."""

    rules: tuple[ValidationRule, ...]

    def run(self, engine: sa.Engine) -> list[ValidationResult]:
        results: list[ValidationResult] = []
        for rule in self.rules:
            executed_at = dt.datetime.now(dt.timezone.utc)
            with engine.connect() as connection:
                rows = connection.execute(sa.text(rule.query), rule.params).mappings().all()
            success, details = _evaluate_checks(rule, rows)
            results.append(
                ValidationResult(
                    name=rule.name,
                    succeeded=success,
                    details=details,
                    executed_at=executed_at,
                )
            )
        return results

    def ensure_success(self, engine: sa.Engine) -> list[ValidationResult]:
        results = self.run(engine)
        failures = [result for result in results if not result.succeeded]
        if failures:
            failed_names = ", ".join(result.name for result in failures)
            raise DataValidationError(f"Data validation failed for: {failed_names}")
        return results

    @classmethod
    def load(cls, path: Path) -> "ValidationSuite":
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        return from_mapping(payload or {})


class DataValidationError(RuntimeError):
    """Raised when validation checks fail."""


def from_mapping(payload: Mapping[str, Any]) -> ValidationSuite:
    rules_payload = payload.get("rules", []) or []
    rules: list[ValidationRule] = []
    for rule in rules_payload:
        checks: list[ValidationCheck] = []
        for check in rule.get("checks", []) or []:
            checks.append(
                ValidationCheck(
                    kind=check["kind"],
                    threshold=check.get("threshold"),
                    equals=check.get("equals"),
                    allowed_values=tuple(check.get("allowed_values", []) or ()),
                    column=check.get("column"),
                )
            )

        rules.append(
            ValidationRule(
                name=rule["name"],
                query=rule["query"],
                params=rule.get("params", {}),
                checks=tuple(checks),
            )
        )

    return ValidationSuite(rules=tuple(rules))


def _evaluate_checks(rule: ValidationRule, rows: Iterable[Mapping[str, Any]]) -> tuple[bool, dict[str, Any]]:
    rows = list(rows)
    details: dict[str, Any] = {"row_count": len(rows)}
    succeeded = True
    for check in rule.checks:
        if check.kind == "row_count_at_least":
            if check.threshold is None:
                raise ValueError(f"Validation '{rule.name}' missing threshold for row_count_at_least")
            passed = len(rows) >= check.threshold
            details[f"row_count_at_least_{check.threshold}"] = passed
            succeeded &= passed
        elif check.kind == "scalar_equals":
            if not rows:
                passed = False
                value = None
            else:
                value = _extract_scalar(rows[0], check)
                passed = value == check.equals
            details[f"scalar_equals_{check.equals}"] = passed
            details[f"observed_{check.column or 'value'}"] = value
            succeeded &= passed
        elif check.kind == "scalar_in":
            if not rows:
                passed = False
                value = None
            else:
                value = _extract_scalar(rows[0], check)
                passed = check.allowed_values and value in check.allowed_values
            details[f"scalar_in_{check.allowed_values}"] = passed
            details[f"observed_{check.column or 'value'}"] = value
            succeeded &= passed
        elif check.kind == "no_nulls":
            column = check.column
            if column is None:
                raise ValueError(f"Validation '{rule.name}' missing column for no_nulls check")
            null_rows = [row for row in rows if row.get(column) is None]
            passed = not null_rows
            details[f"no_nulls_{column}"] = passed
            succeeded &= passed
        else:
            raise ValueError(f"Unknown validation kind: {check.kind}")
    return succeeded, details


def _extract_scalar(row: Mapping[str, Any], check: ValidationCheck) -> Any:
    if check.column:
        return row.get(check.column)
    if len(row) == 1:
        return next(iter(row.values()))
    raise ValueError("Scalar checks require explicit column when query returns multiple columns")
