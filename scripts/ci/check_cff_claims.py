#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Forbidden-claim scan over CITATION.cff (REL-009).

The release citation metadata is a status surface: its ``title``, ``abstract``,
and ``keywords`` are read by academic / industry citers and must not overclaim
past the honest project maturity (``current_state: RESEARCH_ALPHA``).

This gate reads the SINGLE SOURCE OF TRUTH for forbidden claim words —
``governance/project_state.yaml`` (``forbidden_claims``) — and flags every
forbidden claim word *used* (not merely mentioned) in the CFF's claim-bearing
fields. It is intentionally standalone from ``check_state_ontology.py``: this
gate targets one file, one field set, and is fail-closed by construction.

Semantics
---------
* SSOT is ``governance/project_state.yaml``. If it cannot be parsed, or lists
  no ``forbidden_claims``, the gate exits 2 (error) — never silently passes.
* Only the claim-bearing fields ``title``, ``abstract`` and ``keywords`` are
  scanned. Author names, DOIs, and the ``references`` bibliography are metadata,
  not claims, and are left alone.
* **Use / mention aware.** A forbidden word is a *mention* (allowed) when it
  appears inside an explicit negation / disclaimer — e.g. ``not a
  production-grade …``, ``never production-ready``, ``no risk-free …`` — which
  is exactly how an honest limitations note has to name the thing it disclaims.
  A bare assertion of the word is a *use* (flagged).
* Any forbidden *use* -> exit 1. Clean -> exit 0.

A deterministic JSON report is printed to stdout in every mode.

Usage::

    python scripts/ci/check_cff_claims.py                 # scan repo CITATION.cff
    python scripts/ci/check_cff_claims.py --cff path/to/CITATION.cff
    python scripts/ci/check_cff_claims.py --report artifacts/.../report.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
STATE_FILE = ROOT / "governance/project_state.yaml"
CFF_FILE = ROOT / "CITATION.cff"

EXIT_OK = 0
EXIT_FLAGGED = 1
EXIT_ERROR = 2

# Claim-bearing fields of a CFF document. Everything else (authors, doi,
# references) is bibliographic metadata, not a status claim.
CLAIM_FIELDS = ("title", "abstract", "keywords")

# Negation / disclaimer cues. When a forbidden word is immediately governed by
# one of these (within a short left-context window), it is a *mention* inside a
# disclaimer, not a *use* — an honest limitations note must be allowed to name
# what it rules out.
_NEGATION_CUES = (
    "not",
    "never",
    "no",
    "without",
    "isn't",
    "isnt",
    "aren't",
    "arent",
    "neither",
    "nor",
    "non",
)
# Left-context window (characters) scanned for a negation cue before a hit.
_NEG_WINDOW = 48


class CffClaimError(Exception):
    """Fail-closed error (unreadable SSOT / CFF, or empty firewall)."""


def load_forbidden_claims(state_path: Path = STATE_FILE) -> list[dict[str, Any]]:
    """Load the forbidden-claim firewall from the SSOT. Fail-closed."""
    try:
        raw = yaml.safe_load(state_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise CffClaimError(f"cannot read/parse SSOT {state_path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise CffClaimError(f"{state_path}: top level must be a mapping")
    firewall = raw.get("forbidden_claims")
    if not isinstance(firewall, list) or not firewall:
        raise CffClaimError(f"{state_path}: forbidden_claims must be a non-empty list")
    claims: list[dict[str, Any]] = []
    for entry in firewall:
        if not isinstance(entry, dict) or "claim" not in entry or "pattern" not in entry:
            raise CffClaimError(f"forbidden_claims entry missing claim/pattern: {entry!r}")
        try:
            compiled = re.compile(entry["pattern"], re.IGNORECASE)
        except re.error as exc:
            raise CffClaimError(f"forbidden claim {entry['claim']!r} bad regex: {exc}") from exc
        claims.append({"claim": entry["claim"], "pattern": entry["pattern"], "_re": compiled})
    return claims


def load_cff(cff_path: Path = CFF_FILE) -> dict[str, Any]:
    """Parse the CFF document. Fail-closed on unreadable / non-mapping."""
    try:
        raw = yaml.safe_load(cff_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise CffClaimError(f"cannot read/parse CFF {cff_path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise CffClaimError(f"{cff_path}: top level must be a mapping")
    return raw


def _field_text(cff: dict[str, Any], field: str) -> str:
    """Flatten a claim field to a single scannable string."""
    value = cff.get(field)
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return " ".join(str(v) for v in value)
    return str(value)


def _is_mention(text: str, start: int) -> bool:
    """True when the hit at ``start`` sits inside a negation / disclaimer.

    Use / mention distinction: a negation cue (``not``, ``never``, ``no`` …)
    appearing as a whole word within the preceding window governs the hit,
    making it a *mention* of a disclaimed term rather than an *assertion*.
    """
    left = text[max(0, start - _NEG_WINDOW) : start].lower()
    # Whole-word cue anywhere in the left window (handles "is not a", "never a",
    # "not production-ready", etc.). Word-boundary anchored to avoid matching
    # e.g. "innovation" for "no".
    for cue in _NEGATION_CUES:
        if re.search(rf"\b{re.escape(cue)}\b", left):
            return True
    return False


def scan_cff(cff: dict[str, Any], firewall: list[dict[str, Any]]) -> dict[str, Any]:
    """Scan claim fields for forbidden-word *uses*. Deterministic report."""
    violations: list[dict[str, Any]] = []
    mentions: list[dict[str, Any]] = []

    for field in CLAIM_FIELDS:
        text = _field_text(cff, field)
        if not text:
            continue
        for entry in firewall:
            for match in entry["_re"].finditer(text):
                record = {
                    "claim": entry["claim"],
                    "field": field,
                    "matched": match.group(0),
                    "pattern": entry["pattern"],
                }
                if _is_mention(text, match.start()):
                    record["disposition"] = "mention"
                    mentions.append(record)
                else:
                    record["disposition"] = "use"
                    violations.append(record)

    key = lambda r: (r["field"], r["claim"], r["matched"].lower())  # noqa: E731
    violations.sort(key=key)
    mentions.sort(key=key)
    return {
        "source": None,  # filled by caller
        "status": "FLAGGED" if violations else "PASS",
        "scanned_fields": list(CLAIM_FIELDS),
        "forbidden_vocabulary": sorted(e["claim"] for e in firewall),
        "violation_count": len(violations),
        "violations": violations,
        "mention_count": len(mentions),
        "mentions": mentions,
    }


def _emit(report: dict[str, Any]) -> None:
    print(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Forbidden-claim scan over CITATION.cff.")
    parser.add_argument("--cff", type=str, default=None, help="CFF file to scan.")
    parser.add_argument("--state-file", type=str, default=None, help="Override SSOT path.")
    parser.add_argument(
        "--report",
        type=str,
        default=None,
        help="Also write the JSON report to this path.",
    )
    args = parser.parse_args(argv)

    state_path = Path(args.state_file) if args.state_file else STATE_FILE
    cff_path = Path(args.cff) if args.cff else CFF_FILE

    try:
        firewall = load_forbidden_claims(state_path)
        cff = load_cff(cff_path)
    except CffClaimError as exc:
        report = {"status": "ERROR", "error": str(exc)}
        _emit(report)
        return EXIT_ERROR

    report = scan_cff(cff, firewall)
    report["source"] = str(cff_path)

    if args.report is not None:
        out = Path(args.report)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    _emit(report)
    return EXIT_FLAGGED if report["violation_count"] else EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
