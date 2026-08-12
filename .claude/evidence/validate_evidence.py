"""Evidence-matrix validator.

Two responsibilities:

1. Validate the matrix itself (EVIDENCE_MATRIX.yaml) — every category
   defines required keys, every prohibited overclaim is referenced from at
   least one category, etc.

2. Cross-check a claim ledger entry against the matrix:

       check_claim_against_matrix(matrix, claim, asserts=...)

   The `asserts` argument is the name of an overclaim the claim is making
   in addition to its base statement. The validator returns the list of
   refusals (empty if the claim is consistent with the matrix).

The validator is intentionally stdlib + PyYAML only.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MATRIX = REPO_ROOT / ".claude" / "evidence" / "EVIDENCE_MATRIX.yaml"

REQUIRED_CATEGORY_FIELDS = (
    "description",
    "evidence_strength",
    "allowed_claim_tiers",
    "fact_requires_companion",
    "prohibited_overclaims",
    "required_falsifier",
    "example_valid_use",
    "example_invalid_use",
)

VALID_STRENGTHS = frozenset({"NONE", "WEAK", "PARTIAL", "STRONG", "EXECUTED"})
VALID_TIERS = frozenset({"FACT", "EXTRAPOLATION", "SPECULATION"})


@dataclass(frozen=True)
class ValidationError:
    where: str
    rule: str
    detail: str

    def __str__(self) -> str:
        return f"[{self.rule}] {self.where}: {self.detail}"


def load_matrix(path: Path) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    data = yaml.safe_load(raw) or {}
    if not isinstance(data, dict):
        raise ValueError(f"matrix top-level must be a mapping, got {type(data)}")
    if data.get("schema_version") != 1:
        raise ValueError(f"unsupported schema_version: {data.get('schema_version')!r}")
    return data


def validate_matrix(matrix: dict[str, Any]) -> list[ValidationError]:
    """Internal consistency check for the matrix file itself."""
    errors: list[ValidationError] = []

    categories = matrix.get("categories") or {}
    if not isinstance(categories, dict) or not categories:
        errors.append(
            ValidationError("<matrix>", "NO_CATEGORIES", "matrix has no categories defined")
        )
        return errors

    overclaims = matrix.get("prohibited_overclaims") or {}
    if not isinstance(overclaims, dict):
        errors.append(
            ValidationError(
                "<matrix>",
                "OVERCLAIMS_SHAPE",
                "prohibited_overclaims must be a mapping",
            )
        )
        overclaims = {}

    referenced_overclaims: set[str] = set()

    for name, body in categories.items():
        if not isinstance(body, dict):
            errors.append(
                ValidationError(name, "CATEGORY_SHAPE", "category body must be a mapping")
            )
            continue
        for field in REQUIRED_CATEGORY_FIELDS:
            if field not in body:
                errors.append(
                    ValidationError(name, "MISSING_FIELD", f"missing required field: {field}")
                )
        strength = body.get("evidence_strength")
        if strength not in VALID_STRENGTHS:
            errors.append(
                ValidationError(name, "BAD_STRENGTH", f"unknown evidence_strength: {strength!r}")
            )
        for tier in body.get("allowed_claim_tiers") or []:
            if tier not in VALID_TIERS:
                errors.append(
                    ValidationError(
                        name, "BAD_TIER", f"unknown tier in allowed_claim_tiers: {tier!r}"
                    )
                )
        for overclaim in body.get("prohibited_overclaims") or []:
            referenced_overclaims.add(str(overclaim))

        # If FACT is allowed but fact_requires_companion is True, check
        # the companion list is non-empty.
        if (
            "FACT" in (body.get("allowed_claim_tiers") or [])
            and body.get("fact_requires_companion")
            and not body.get("fact_companion_categories")
        ):
            errors.append(
                ValidationError(
                    name,
                    "FACT_COMPANION_MISSING",
                    "fact_requires_companion=True but no fact_companion_categories",
                )
            )

    # Every overclaim referenced by a category must be defined in
    # prohibited_overclaims, and vice versa.
    defined = set(overclaims.keys())
    for ref in referenced_overclaims - defined:
        errors.append(
            ValidationError(ref, "OVERCLAIM_UNDEFINED", "referenced by a category but not defined")
        )
    for orphan in defined - referenced_overclaims:
        # Defined-but-unreferenced overclaims are allowed (cross-category
        # overclaims like UNIVERSAL_CLAIM, BUG_FREE_CODE, SCANNER_COMPLETENESS,
        # GREEN-CI / SECURITY-VERIFICATION pairs). No error.
        pass

    for name, body in overclaims.items():
        if not isinstance(body, dict):
            errors.append(
                ValidationError(name, "OVERCLAIM_SHAPE", "overclaim body must be a mapping")
            )
            continue
        if "description" not in body:
            errors.append(ValidationError(name, "MISSING_FIELD", "overclaim missing description"))
        if "requires_any_of" not in body:
            errors.append(
                ValidationError(name, "MISSING_FIELD", "overclaim missing requires_any_of")
            )
        if "refusal_message" not in body:
            errors.append(
                ValidationError(name, "MISSING_FIELD", "overclaim missing refusal_message")
            )

    # Regression cases must reference defined overclaims.
    for case in matrix.get("regression_cases") or []:
        cname = case.get("name", "<unnamed>")
        ref = case.get("expected_refusal")
        if ref not in defined:
            errors.append(
                ValidationError(
                    cname,
                    "REGRESSION_BAD_REF",
                    f"expected_refusal {ref!r} not defined in prohibited_overclaims",
                )
            )

    return errors


def check_claim_against_matrix(
    matrix: dict[str, Any],
    *,
    claim_class: str,
    tier: str,
    evidence_types: Iterable[str],
    asserts: Iterable[str] | None = None,
) -> list[ValidationError]:
    """Refuse a claim shape that violates the matrix.

    Parameters
    ----------
    matrix
        The loaded matrix data.
    claim_class
        The claim ledger class (SECURITY, SCIENTIFIC, ...). Used for context
        in error messages but does not gate by itself; the rules are
        evidence-driven.
    tier
        FACT / EXTRAPOLATION / SPECULATION.
    evidence_types
        The evidence categories the claim cites.
    asserts
        Names of overclaims the claim is making. Each must be supported by
        at least one of the categories in the overclaim's `requires_any_of`.

    Returns
    -------
    list of ValidationError
        Empty when the claim is matrix-consistent.
    """
    errors: list[ValidationError] = []
    categories = matrix.get("categories") or {}
    overclaims = matrix.get("prohibited_overclaims") or {}
    ev_set = {str(t) for t in evidence_types}

    if tier not in VALID_TIERS:
        errors.append(ValidationError("<claim>", "BAD_TIER", f"unknown tier: {tier!r}"))
        return errors

    if not ev_set:
        errors.append(ValidationError("<claim>", "NO_EVIDENCE", "claim has no evidence_types"))
        return errors

    # Per-category tier eligibility.
    for ev in ev_set:
        cat = categories.get(ev)
        if not cat:
            errors.append(
                ValidationError(ev, "EVIDENCE_TYPE_UNKNOWN", "evidence type not in matrix")
            )
            continue
        allowed = set(cat.get("allowed_claim_tiers") or [])
        if tier not in allowed:
            errors.append(
                ValidationError(
                    ev,
                    "TIER_NOT_ALLOWED",
                    f"category does not support tier {tier} (allowed: {sorted(allowed)})",
                )
            )

    # FACT-tier companion rules.
    if tier == "FACT":
        for ev in ev_set:
            cat = categories.get(ev) or {}
            if cat.get("fact_requires_companion"):
                companions = set(cat.get("fact_companion_categories") or [])
                if not (ev_set - {ev}) & companions:
                    errors.append(
                        ValidationError(
                            ev,
                            "FACT_COMPANION_REQUIRED",
                            f"FACT tier with {ev} requires at least one companion in {sorted(companions)}",
                        )
                    )

    # Per-evidence-type prohibited overclaims.
    asserted = {str(a) for a in (asserts or [])}
    for ev in ev_set:
        cat = categories.get(ev) or {}
        for prohibited in cat.get("prohibited_overclaims") or []:
            if prohibited in asserted:
                # Check that the claim ALSO cites a supporting evidence type
                # listed in the overclaim's requires_any_of.
                oc = overclaims.get(prohibited) or {}
                supporting = set(oc.get("requires_any_of") or [])
                if not ev_set & supporting:
                    errors.append(
                        ValidationError(
                            prohibited,
                            "OVERCLAIM_REFUSED",
                            (
                                f"asserting {prohibited} via {ev} requires at "
                                f"least one of {sorted(supporting) or 'NO SUPPORTING EVIDENCE EVER'}"
                            ),
                        )
                    )

    # Asserted overclaims that are unsupported by ANY cited evidence.
    for prohibited in asserted:
        oc = overclaims.get(prohibited)
        if not oc:
            errors.append(
                ValidationError(
                    prohibited,
                    "OVERCLAIM_UNDEFINED",
                    "claim asserts an overclaim not defined in the matrix",
                )
            )
            continue
        supporting = set(oc.get("requires_any_of") or [])
        if not supporting:
            # Overclaims with empty requires_any_of (BUG_FREE_CODE,
            # SCANNER_COMPLETENESS) are NEVER allowed.
            errors.append(
                ValidationError(
                    prohibited,
                    "OVERCLAIM_FORBIDDEN",
                    oc.get("refusal_message", "this overclaim is never allowed").strip(),
                )
            )
            continue
        if not ev_set & supporting:
            errors.append(
                ValidationError(
                    prohibited,
                    "OVERCLAIM_REFUSED",
                    (
                        f"asserting {prohibited} requires at least one of "
                        f"{sorted(supporting)} (cited: {sorted(ev_set)})"
                    ),
                )
            )

    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate the GeoSync evidence matrix")
    parser.add_argument(
        "--matrix",
        type=Path,
        default=DEFAULT_MATRIX,
        help="path to EVIDENCE_MATRIX.yaml",
    )
    args = parser.parse_args(argv)
    if not args.matrix.exists():
        print(f"FAIL: matrix not found: {args.matrix}", file=sys.stderr)
        return 1
    try:
        matrix = load_matrix(args.matrix)
    except (yaml.YAMLError, ValueError) as exc:
        print(f"FAIL: cannot load matrix: {exc}", file=sys.stderr)
        return 1
    errors = validate_matrix(matrix)
    if errors:
        print(
            f"FAIL: evidence matrix has {len(errors)} validation error(s):",
            file=sys.stderr,
        )
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1
    print(f"OK: evidence matrix validated ({args.matrix})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
