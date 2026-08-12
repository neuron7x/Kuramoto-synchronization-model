"""Translation-matrix validator for the GeoSync Physics-2026 evidence rail.

Validates `.claude/research/PHYSICS_2026_TRANSLATION.yaml` against the
translation contract defined by the Physics-2026 protocol:

  1. The file parses as YAML and declares schema_version: 1.

  2. Every pattern entry has the required keys:
        pattern_id, source_ids, source_fact_summary,
        methodological_pattern, geosync_operational_analog,
        proposed_module, claim_tier, implementation_status,
        measurable_inputs, output_witness, null_model, falsifier,
        deterministic_tests, mutation_candidate, ledger_entry_required

  3. Every source_id referenced by a pattern exists in the source pack.

  4. Every pattern with implementation_status != REJECTED has at least
     one measurable_input, one output_witness, a non-empty null_model,
     a non-empty falsifier, and at least one deterministic_test.

  5. ENGINEERING_ANALOG patterns must NOT use forbidden phrasings:
        "physical equivalence", "quantum market", "universal", "predicts returns"
     anywhere in the body.

  6. HYPOTHESIS patterns must NOT be marked FACT.

  7. REJECTED patterns must include `rejection_reason`.

  8. proposed_module paths are unique across all patterns.

  9. claim_tier is one of:
        FACT / ENGINEERING_ANALOG / HYPOTHESIS / REJECTED

 10. implementation_status is one of:
        PROPOSED / IMPLEMENTED / REJECTED

The validator is stdlib + PyYAML only. Output is deterministic JSON
written to /tmp/geosync_physics2026_translation_validation.json.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TRANSLATION = REPO_ROOT / ".claude" / "research" / "PHYSICS_2026_TRANSLATION.yaml"
DEFAULT_SOURCE_PACK = REPO_ROOT / "docs" / "research" / "physics_2026" / "source_pack.yaml"
DEFAULT_OUTPUT = Path("/tmp/geosync_physics2026_translation_validation.json")

REQUIRED_KEYS: tuple[str, ...] = (
    "pattern_id",
    "source_ids",
    "source_fact_summary",
    "methodological_pattern",
    "geosync_operational_analog",
    "proposed_module",
    "claim_tier",
    "implementation_status",
    "measurable_inputs",
    "output_witness",
    "null_model",
    "falsifier",
    "deterministic_tests",
    "mutation_candidate",
    "ledger_entry_required",
)

VALID_CLAIM_TIERS = frozenset({"FACT", "ENGINEERING_ANALOG", "HYPOTHESIS", "REJECTED"})
VALID_IMPLEMENTATION_STATUS = frozenset({"PROPOSED", "IMPLEMENTED", "REJECTED"})

# Phrasings that must never appear inside an ENGINEERING_ANALOG body.
# These are the calibration-layer red lines: ENGINEERING_ANALOG must not
# inflate into either physical equivalence or predictive overclaim.
FORBIDDEN_PHRASES_IN_ANALOG: tuple[str, ...] = (
    "physical equivalence",
    "quantum market",
    "universal",
    "predicts returns",
    "new law of physics",
    "noise improves intelligence",
    "kpz proves market",
    "longer reasoning is always better",
)


@dataclass(frozen=True)
class ValidationError:
    where: str
    rule: str
    detail: str

    def __str__(self) -> str:
        return f"[{self.rule}] {self.where}: {self.detail}"


@dataclass
class ValidationReport:
    pattern_count: int = 0
    valid: bool = True
    errors: list[ValidationError] = field(default_factory=list)
    warnings: list[ValidationError] = field(default_factory=list)
    pattern_ids: list[str] = field(default_factory=list)
    referenced_source_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pattern_count": self.pattern_count,
            "valid": self.valid,
            "errors": [str(e) for e in self.errors],
            "warnings": [str(w) for w in self.warnings],
            "pattern_ids": sorted(self.pattern_ids),
            "referenced_source_ids": sorted(self.referenced_source_ids),
        }


def _load_known_source_ids(pack_path: Path) -> set[str]:
    if not pack_path.exists():
        return set()
    try:
        data = yaml.safe_load(pack_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return set()
    sources = data.get("sources") or []
    if not isinstance(sources, list):
        return set()
    return {
        str(s.get("source_id"))
        for s in sources
        if isinstance(s, dict) and isinstance(s.get("source_id"), str)
    }


def _walk_strings(obj: Any) -> Iterable[str]:
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _walk_strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk_strings(v)


def _check_required_keys(pattern: dict[str, Any]) -> list[ValidationError]:
    errors: list[ValidationError] = []
    pid = str(pattern.get("pattern_id") or "<unknown>")
    for key in REQUIRED_KEYS:
        if key not in pattern:
            errors.append(ValidationError(pid, "MISSING_KEY", f"required key absent: {key}"))
    return errors


def _check_source_refs(
    pattern: dict[str, Any], known_source_ids: set[str]
) -> list[ValidationError]:
    errors: list[ValidationError] = []
    pid = str(pattern.get("pattern_id") or "<unknown>")
    refs = pattern.get("source_ids") or []
    if not isinstance(refs, list) or not refs:
        errors.append(
            ValidationError(
                pid,
                "EMPTY_SOURCE_IDS",
                "source_ids must be a non-empty list",
            )
        )
        return errors
    for ref in refs:
        if not isinstance(ref, str):
            errors.append(ValidationError(pid, "BAD_SOURCE_ID_SHAPE", f"non-string entry: {ref!r}"))
            continue
        if ref not in known_source_ids:
            errors.append(
                ValidationError(
                    pid,
                    "UNKNOWN_SOURCE_ID",
                    f"source_id {ref!r} not present in source pack",
                )
            )
    return errors


def _check_claim_tier(pattern: dict[str, Any]) -> list[ValidationError]:
    errors: list[ValidationError] = []
    pid = str(pattern.get("pattern_id") or "<unknown>")
    tier = pattern.get("claim_tier")
    if tier not in VALID_CLAIM_TIERS:
        errors.append(ValidationError(pid, "BAD_CLAIM_TIER", f"unknown claim_tier: {tier!r}"))
    return errors


def _check_implementation_status(
    pattern: dict[str, Any],
) -> list[ValidationError]:
    errors: list[ValidationError] = []
    pid = str(pattern.get("pattern_id") or "<unknown>")
    status = pattern.get("implementation_status")
    if status not in VALID_IMPLEMENTATION_STATUS:
        errors.append(
            ValidationError(
                pid,
                "BAD_IMPLEMENTATION_STATUS",
                f"unknown implementation_status: {status!r}",
            )
        )
    return errors


def _check_evidence_payload(pattern: dict[str, Any]) -> list[ValidationError]:
    """For any pattern that is NOT REJECTED, the evidence payload must be
    non-empty: at least one measurable_input, one output_witness, a
    non-empty null_model, a non-empty falsifier, and at least one
    deterministic_test."""
    errors: list[ValidationError] = []
    pid = str(pattern.get("pattern_id") or "<unknown>")
    if pattern.get("implementation_status") == "REJECTED":
        return errors
    if pattern.get("claim_tier") == "REJECTED":
        return errors

    list_fields = (
        ("measurable_inputs", "EMPTY_MEASURABLE_INPUTS"),
        ("output_witness", "EMPTY_OUTPUT_WITNESS"),
        ("deterministic_tests", "EMPTY_DETERMINISTIC_TESTS"),
    )
    for key, rule in list_fields:
        value = pattern.get(key)
        if not isinstance(value, list) or not value:
            errors.append(
                ValidationError(
                    pid, rule, f"{key} must be a non-empty list for non-REJECTED pattern"
                )
            )
    string_fields = (
        ("null_model", "EMPTY_NULL_MODEL"),
        ("falsifier", "EMPTY_FALSIFIER"),
    )
    for key, rule in string_fields:
        value = pattern.get(key)
        if not isinstance(value, str) or not value.strip():
            errors.append(
                ValidationError(
                    pid,
                    rule,
                    f"{key} must be a non-empty string for non-REJECTED pattern",
                )
            )
    return errors


def _check_engineering_analog_phrasing(
    pattern: dict[str, Any],
) -> list[ValidationError]:
    errors: list[ValidationError] = []
    pid = str(pattern.get("pattern_id") or "<unknown>")
    if pattern.get("claim_tier") != "ENGINEERING_ANALOG":
        return errors
    # Inspect the analog body. We DO NOT scan source_fact_summary because it
    # may legitimately quote the source description (e.g. "universal").
    inspected_keys = (
        "geosync_operational_analog",
        "methodological_pattern",
        "null_model",
        "falsifier",
    )
    for key in inspected_keys:
        value = pattern.get(key)
        if value is None:
            continue
        for text in _walk_strings(value):
            lower = text.lower()
            for phrase in FORBIDDEN_PHRASES_IN_ANALOG:
                if phrase in lower:
                    errors.append(
                        ValidationError(
                            pid,
                            "FORBIDDEN_ANALOG_PHRASE",
                            f"{key} contains forbidden phrasing: {phrase!r}",
                        )
                    )
    return errors


def _check_hypothesis_not_fact(
    pattern: dict[str, Any],
) -> list[ValidationError]:
    """Belt-and-braces. If the pattern is a HYPOTHESIS but somewhere
    declares itself FACT (e.g. via a stray field or a status mismatch),
    refuse it. This catches the easiest path for claim inflation."""
    errors: list[ValidationError] = []
    pid = str(pattern.get("pattern_id") or "<unknown>")
    tier = pattern.get("claim_tier")
    # Cross-check explicit `claim_tier` against any contradicting marker.
    legacy_tier = pattern.get("legacy_claim_tier")
    if tier == "HYPOTHESIS" and legacy_tier == "FACT":
        errors.append(
            ValidationError(
                pid,
                "HYPOTHESIS_MARKED_FACT",
                "claim_tier is HYPOTHESIS but legacy_claim_tier is FACT",
            )
        )
    return errors


def _check_rejected_has_reason(
    pattern: dict[str, Any],
) -> list[ValidationError]:
    errors: list[ValidationError] = []
    pid = str(pattern.get("pattern_id") or "<unknown>")
    if (
        pattern.get("claim_tier") == "REJECTED"
        or pattern.get("implementation_status") == "REJECTED"
    ):
        reason = pattern.get("rejection_reason")
        if not isinstance(reason, str) or not reason.strip():
            errors.append(
                ValidationError(
                    pid,
                    "REJECTED_NO_REASON",
                    "REJECTED pattern must include a non-empty rejection_reason",
                )
            )
    return errors


def _check_unique_module_paths(
    patterns: list[dict[str, Any]],
) -> list[ValidationError]:
    errors: list[ValidationError] = []
    seen: dict[str, str] = {}
    for pattern in patterns:
        path = pattern.get("proposed_module")
        if not isinstance(path, str):
            continue
        pid = str(pattern.get("pattern_id") or "<unknown>")
        if path in seen:
            errors.append(
                ValidationError(
                    pid,
                    "DUPLICATE_MODULE_PATH",
                    f"proposed_module {path!r} also used by {seen[path]}",
                )
            )
        else:
            seen[path] = pid
    return errors


def _check_unique_pattern_ids(
    patterns: list[dict[str, Any]],
) -> list[ValidationError]:
    errors: list[ValidationError] = []
    counts: dict[str, int] = {}
    for pattern in patterns:
        pid = pattern.get("pattern_id")
        if not isinstance(pid, str):
            continue
        counts[pid] = counts.get(pid, 0) + 1
    for pid, count in counts.items():
        if count > 1:
            errors.append(
                ValidationError(
                    pid,
                    "DUPLICATE_PATTERN_ID",
                    f"pattern_id appears {count} times",
                )
            )
    return errors


def validate_translation(
    translation_path: Path,
    source_pack_path: Path | None = None,
) -> ValidationReport:
    if not translation_path.exists():
        return ValidationReport(
            valid=False,
            errors=[
                ValidationError(
                    "<translation>",
                    "TRANSLATION_NOT_FOUND",
                    str(translation_path),
                )
            ],
        )
    try:
        data = yaml.safe_load(translation_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        return ValidationReport(
            valid=False,
            errors=[ValidationError("<translation>", "YAML_PARSE_ERROR", str(exc))],
        )
    if not isinstance(data, dict):
        return ValidationReport(
            valid=False,
            errors=[
                ValidationError(
                    "<translation>",
                    "TRANSLATION_SHAPE",
                    "top-level must be a mapping",
                )
            ],
        )
    if data.get("schema_version") != 1:
        return ValidationReport(
            valid=False,
            errors=[
                ValidationError(
                    "<translation>",
                    "SCHEMA_VERSION",
                    f"unsupported schema_version: {data.get('schema_version')!r}",
                )
            ],
        )
    patterns = data.get("patterns") or []
    if not isinstance(patterns, list):
        return ValidationReport(
            valid=False,
            errors=[
                ValidationError(
                    "<translation>",
                    "PATTERNS_SHAPE",
                    "patterns must be a list",
                )
            ],
        )

    pack = source_pack_path or DEFAULT_SOURCE_PACK
    known_source_ids = _load_known_source_ids(pack)
    if not known_source_ids:
        return ValidationReport(
            valid=False,
            errors=[
                ValidationError(
                    "<translation>",
                    "SOURCE_PACK_UNAVAILABLE",
                    f"could not load any source ids from {pack}",
                )
            ],
        )

    errors: list[ValidationError] = []
    for pattern in patterns:
        if not isinstance(pattern, dict):
            errors.append(
                ValidationError(
                    "<unknown>",
                    "PATTERN_SHAPE",
                    f"pattern entry must be a mapping: {pattern!r}",
                )
            )
            continue
        errors.extend(_check_required_keys(pattern))
        errors.extend(_check_claim_tier(pattern))
        errors.extend(_check_implementation_status(pattern))
        errors.extend(_check_source_refs(pattern, known_source_ids))
        errors.extend(_check_evidence_payload(pattern))
        errors.extend(_check_engineering_analog_phrasing(pattern))
        errors.extend(_check_hypothesis_not_fact(pattern))
        errors.extend(_check_rejected_has_reason(pattern))
    errors.extend(_check_unique_module_paths(patterns))
    errors.extend(_check_unique_pattern_ids(patterns))

    pattern_ids: list[str] = []
    referenced: set[str] = set()
    for pattern in patterns:
        if not isinstance(pattern, dict):
            continue
        pid = pattern.get("pattern_id")
        if isinstance(pid, str):
            pattern_ids.append(pid)
        for ref in pattern.get("source_ids") or []:
            if isinstance(ref, str):
                referenced.add(ref)

    return ValidationReport(
        pattern_count=len(patterns),
        valid=not errors,
        errors=errors,
        warnings=[],
        pattern_ids=pattern_ids,
        referenced_source_ids=sorted(referenced),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate the GeoSync Physics-2026 translation matrix",
    )
    parser.add_argument(
        "--translation",
        type=Path,
        default=DEFAULT_TRANSLATION,
        help="path to PHYSICS_2026_TRANSLATION.yaml",
    )
    parser.add_argument(
        "--source-pack",
        type=Path,
        default=DEFAULT_SOURCE_PACK,
        help="path to source_pack.yaml (used to verify source_id refs)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
    )
    args = parser.parse_args(argv)
    report = validate_translation(args.translation, args.source_pack)
    payload = json.dumps(report.to_dict(), indent=2, sort_keys=True)
    args.output.write_text(payload + "\n", encoding="utf-8")
    if not report.valid:
        print(
            f"FAIL: translation has {len(report.errors)} validation error(s):",
            file=sys.stderr,
        )
        for err in report.errors:
            print(f"  - {err}", file=sys.stderr)
        return 1
    print(
        f"OK: translation matrix validated "
        f"({report.pattern_count} patterns, {len(report.referenced_source_ids)} source refs)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
