"""Source-pack validator for the GeoSync Physics-2026 evidence rail.

Validates `docs/research/physics_2026/source_pack.yaml` against six
mechanical contracts:

  1. The file parses as YAML and declares schema_version: 1.
  2. Every source has the required keys:
        source_id, title, url, verified_fact, allowed_translation,
        forbidden_overclaim
  3. Every source has at least one entry in each of the three
     evidence lists (verified_fact / allowed_translation /
     forbidden_overclaim).
  4. No source's prose contains forbidden overclaim phrasings:
        "proves market", "quantum market", "predicts returns",
        "universal law", "physical equivalence"
  5. source_id values are non-empty, unique, and stable
     (`S<digit>_<UPPERCASE_TOKEN>` shape).
  6. Output is deterministic JSON written to:
        /tmp/geosync_physics2026_source_validation.json

Exit code is non-zero when any contract is violated.

The validator is stdlib + PyYAML only. No project imports.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE_PACK = REPO_ROOT / "docs" / "research" / "physics_2026" / "source_pack.yaml"
DEFAULT_OUTPUT = Path("/tmp/geosync_physics2026_source_validation.json")

REQUIRED_KEYS: tuple[str, ...] = (
    "source_id",
    "title",
    "url",
    "verified_fact",
    "allowed_translation",
    "forbidden_overclaim",
)

# Phrasings that must NEVER appear in the source pack body, regardless of
# which key they sit under. They are the calibration-layer's red lines:
# the source pack is an evidence rail, not a marketing document.
FORBIDDEN_PHRASES: tuple[str, ...] = (
    "proves market",
    "quantum market",
    "predicts returns",
    "universal law",
    "physical equivalence",
    "new law of physics",
    "noise improves intelligence",
    "kpz proves market",
    "longer reasoning is always better",
)

# Stable shape: S followed by one or more digits, an underscore, and an
# UPPERCASE token (letters + digits + underscores).
_SOURCE_ID_SHAPE = re.compile(r"^S\d+_[A-Z][A-Z0-9_]*$")


@dataclass(frozen=True)
class ValidationError:
    where: str
    rule: str
    detail: str

    def __str__(self) -> str:
        return f"[{self.rule}] {self.where}: {self.detail}"


@dataclass
class ValidationReport:
    source_count: int = 0
    valid: bool = True
    errors: list[ValidationError] = field(default_factory=list)
    warnings: list[ValidationError] = field(default_factory=list)
    source_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_count": self.source_count,
            "valid": self.valid,
            "errors": [str(e) for e in self.errors],
            "warnings": [str(w) for w in self.warnings],
            "source_ids": sorted(self.source_ids),
        }


def _check_required_keys(source: dict[str, Any]) -> list[ValidationError]:
    errors: list[ValidationError] = []
    sid = str(source.get("source_id") or "<missing>")
    for key in REQUIRED_KEYS:
        if key not in source:
            errors.append(ValidationError(sid, "MISSING_KEY", f"required key absent: {key}"))
            continue
        value = source[key]
        if key in {"verified_fact", "allowed_translation", "forbidden_overclaim"}:
            if not isinstance(value, list) or not value:
                errors.append(
                    ValidationError(
                        sid,
                        "EMPTY_EVIDENCE_LIST",
                        f"{key} must be a non-empty list",
                    )
                )
        else:
            if not isinstance(value, str) or not value.strip():
                errors.append(
                    ValidationError(
                        sid,
                        "EMPTY_SCALAR",
                        f"{key} must be a non-empty string",
                    )
                )
    return errors


def _walk_strings(obj: Any) -> Iterable[str]:
    """Yield every string in a nested dict/list structure."""
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _walk_strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk_strings(v)


def _check_forbidden_phrases(source: dict[str, Any]) -> list[ValidationError]:
    """Scan every string in the source for forbidden phrasings.

    The check is case-insensitive but otherwise a literal substring match.
    Documenting a forbidden phrase by quoting it (e.g. in `forbidden_overclaim`)
    is allowed: the phrase scanner is applied to ALL keys including
    `forbidden_overclaim`, but only the `verified_fact`, `allowed_translation`,
    `title`, and free prose strings count for failure. This way an entry can
    explicitly forbid the phrasing without tripping the gate.
    """
    errors: list[ValidationError] = []
    sid = str(source.get("source_id") or "<missing>")
    inspected_keys = ("title", "verified_fact", "allowed_translation")
    for key in inspected_keys:
        value = source.get(key)
        if value is None:
            continue
        for text in _walk_strings(value):
            lower = text.lower()
            for phrase in FORBIDDEN_PHRASES:
                if phrase in lower:
                    errors.append(
                        ValidationError(
                            sid,
                            "FORBIDDEN_PHRASE",
                            f"{key} contains forbidden phrasing: {phrase!r}",
                        )
                    )
    return errors


def _check_source_id_shape(source: dict[str, Any]) -> list[ValidationError]:
    sid = source.get("source_id")
    if not isinstance(sid, str) or not sid.strip():
        return [ValidationError("<unknown>", "BAD_SOURCE_ID", "missing source_id")]
    if not _SOURCE_ID_SHAPE.match(sid):
        return [
            ValidationError(
                sid,
                "BAD_SOURCE_ID_SHAPE",
                f"source_id {sid!r} does not match S<digits>_<UPPER_TOKEN>",
            )
        ]
    return []


def _check_unique_ids(sources: list[dict[str, Any]]) -> list[ValidationError]:
    errors: list[ValidationError] = []
    seen: dict[str, int] = {}
    for source in sources:
        sid = source.get("source_id")
        if not isinstance(sid, str):
            continue
        seen[sid] = seen.get(sid, 0) + 1
    for sid, count in seen.items():
        if count > 1:
            errors.append(
                ValidationError(
                    sid,
                    "DUPLICATE_SOURCE_ID",
                    f"source_id appears {count} times",
                )
            )
    return errors


def validate_pack(pack_path: Path) -> ValidationReport:
    if not pack_path.exists():
        return ValidationReport(
            valid=False,
            errors=[ValidationError("<pack>", "PACK_NOT_FOUND", str(pack_path))],
        )
    raw_text = pack_path.read_text(encoding="utf-8")
    try:
        data = yaml.safe_load(raw_text) or {}
    except yaml.YAMLError as exc:
        return ValidationReport(
            valid=False,
            errors=[ValidationError("<pack>", "YAML_PARSE_ERROR", str(exc))],
        )
    if not isinstance(data, dict):
        return ValidationReport(
            valid=False,
            errors=[ValidationError("<pack>", "PACK_SHAPE", "top-level must be a mapping")],
        )
    if data.get("schema_version") != 1:
        return ValidationReport(
            valid=False,
            errors=[
                ValidationError(
                    "<pack>",
                    "SCHEMA_VERSION",
                    f"unsupported schema_version: {data.get('schema_version')!r}",
                )
            ],
        )
    sources = data.get("sources") or []
    if not isinstance(sources, list):
        return ValidationReport(
            valid=False,
            errors=[ValidationError("<pack>", "SOURCES_SHAPE", "sources must be a list")],
        )

    errors: list[ValidationError] = []
    for source in sources:
        if not isinstance(source, dict):
            errors.append(
                ValidationError(
                    "<unknown>",
                    "SOURCE_SHAPE",
                    f"source entry must be a mapping: {source!r}",
                )
            )
            continue
        errors.extend(_check_source_id_shape(source))
        errors.extend(_check_required_keys(source))
        errors.extend(_check_forbidden_phrases(source))
    errors.extend(_check_unique_ids(sources))

    source_ids = [
        str(s.get("source_id"))
        for s in sources
        if isinstance(s, dict) and isinstance(s.get("source_id"), str)
    ]

    return ValidationReport(
        source_count=len(sources),
        valid=not errors,
        errors=errors,
        warnings=[],
        source_ids=source_ids,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate the GeoSync Physics-2026 source pack",
    )
    parser.add_argument(
        "--pack",
        type=Path,
        default=DEFAULT_SOURCE_PACK,
        help="path to source_pack.yaml",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="path to write JSON report",
    )
    args = parser.parse_args(argv)
    report = validate_pack(args.pack)
    payload = json.dumps(report.to_dict(), indent=2, sort_keys=True)
    args.output.write_text(payload + "\n", encoding="utf-8")
    if not report.valid:
        print(
            f"FAIL: source pack has {len(report.errors)} validation error(s):",
            file=sys.stderr,
        )
        for err in report.errors:
            print(f"  - {err}", file=sys.stderr)
        return 1
    print(
        f"OK: source pack validated "
        f"({report.source_count} sources, {len(report.source_ids)} unique IDs)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
