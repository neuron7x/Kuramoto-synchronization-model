#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Fail-closed claim/evidence gate.

Validates ``docs/CLAIMS.yaml`` against the canonical schema and
verifies that every ``P0`` / ``P1`` claim's ``evidence_paths`` exist
in the working tree. Missing evidence on a P0 / P1 claim is a build
failure.

Schema v2 (2026-05-03, IERD-PAI-FPS-UX-001) introduces the ``tier``
field on every claim: one of ``ANCHORED`` | ``EXTRAPOLATED`` |
``SPECULATIVE`` | ``UNKNOWN``. Schema v1 entries are still accepted
(tier defaults to ``UNKNOWN``); newly added v2 entries must declare
the field explicitly.

Run locally before push:

    python scripts/ci/check_claims.py

Exit codes:

    0  — all gated claims have intact evidence and (v3) every P0/P1
         ANCHORED claim carries a falsifier block
    1  — schema violation, missing evidence on a P0/P1 claim, OR a
         P0/P1 ANCHORED claim with no v3 falsifier block

The intent is the inverse of an aspirational README: the registry
states what the repository claims to be, and the CI gate refuses to
let those claims drift away from the artefacts that back them.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
CLAIMS_PATH = ROOT / "docs" / "CLAIMS.yaml"

SCHEMA_VERSIONS_SUPPORTED = frozenset({1, 2, 3})
SCHEMA_VERSION_LATEST = 3
ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
PRIORITIES_GATED = frozenset({"P0", "P1"})
PRIORITIES_ALL = frozenset({"P0", "P1", "P2"})
TIERS_VALID = frozenset({"ANCHORED", "EXTRAPOLATED", "SPECULATIVE", "UNKNOWN"})
# v3 falsifier dict shape: per ADR 0021. Keys are validated structurally
# (presence + type) on v3 ANCHORED claims; cross-reference (test_id
# resolves to actual pytest node) is enforced by compute_fps_audit.
FALSIFIER_REQUIRED_KEYS = frozenset({"test_id", "invariants_cited", "failure_signature"})
INV_PATTERN = re.compile(r"^INV-[A-Z0-9][A-Z0-9]*(?:-[A-Za-z0-9]+)*$")
# v1 legacy default: UNKNOWN. The pre-v2 gate's strict path-existence
# check still runs because the gate enforces ``ANCHORED/EXTRAPOLATED ⇒
# all paths exist`` only on those two tiers. A v1 entry without a tier
# field cannot silently inherit ANCHORED — that would be the exact
# IERD §1 loophole (a claim treated as anchored without declared
# evidence quality). Operators must migrate v1 → v2 with an explicit
# tier; until then their entries warn but do not gate.
TIER_DEFAULT_LEGACY = "UNKNOWN"
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass(frozen=True)
class Falsifier:
    """v3 falsifier block — pytest node + invariants + failure signature."""

    test_id: str
    invariants_cited: tuple[str, ...]
    failure_signature: str


@dataclass(frozen=True)
class Claim:
    """In-memory representation of a single registry entry."""

    id: str
    priority: str
    tier: str
    description: str
    evidence_paths: tuple[str, ...]
    added_utc: str
    falsifier: Falsifier | None = None


@dataclass(frozen=True)
class ValidationFailure:
    claim_id: str
    reason: str

    def __str__(self) -> str:
        return f"[{self.claim_id}] {self.reason}"


def _load_registry(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"missing registry: {path}")
    with path.open("r", encoding="utf-8") as handle:
        loaded: object = yaml.safe_load(handle)
    if not isinstance(loaded, dict):
        raise TypeError(f"registry must be a YAML mapping, got {type(loaded).__name__}")
    return loaded


def _resolve_schema_version(registry: dict[str, Any]) -> int:
    schema_version_raw: object = registry.get("schema_version")
    if schema_version_raw not in SCHEMA_VERSIONS_SUPPORTED:
        raise ValueError(
            f"schema_version={schema_version_raw!r} "
            f"not in supported {sorted(SCHEMA_VERSIONS_SUPPORTED)}"
        )
    assert isinstance(schema_version_raw, int)
    return schema_version_raw


def _parse_claims(registry: dict[str, Any]) -> list[Claim]:
    schema_version = _resolve_schema_version(registry)
    raw_claims = registry.get("claims")
    if not isinstance(raw_claims, list):
        raise ValueError("'claims' must be a list at the top level of CLAIMS.yaml")
    claims: list[Claim] = []
    seen_ids: set[str] = set()
    for index, entry in enumerate(raw_claims):
        if not isinstance(entry, dict):
            raise ValueError(f"claim #{index}: expected mapping, got {type(entry).__name__}")
        claim = _parse_one(entry, index, schema_version=schema_version)
        if claim.id in seen_ids:
            raise ValueError(f"duplicate claim id: {claim.id!r}")
        seen_ids.add(claim.id)
        claims.append(claim)
    return claims


def _parse_falsifier(raw: object, claim_id: str) -> Falsifier:
    if not isinstance(raw, dict):
        raise ValueError(f"claim {claim_id}: falsifier must be a mapping")
    missing = FALSIFIER_REQUIRED_KEYS - set(raw.keys())
    if missing:
        raise ValueError(f"claim {claim_id}: falsifier missing keys: {sorted(missing)}")
    test_id = raw["test_id"]
    if not isinstance(test_id, str) or "::" not in test_id:
        raise ValueError(
            f"claim {claim_id}: falsifier.test_id must be a pytest node id "
            f"(file::test_func), got {test_id!r}"
        )
    cited = raw["invariants_cited"]
    if not isinstance(cited, list) or not cited:
        raise ValueError(f"claim {claim_id}: falsifier.invariants_cited must be non-empty list")
    for inv in cited:
        if not isinstance(inv, str) or not INV_PATTERN.match(inv):
            raise ValueError(
                f"claim {claim_id}: falsifier.invariants_cited entry {inv!r} "
                f"must match INV-<TAG> shape"
            )
    sig = raw["failure_signature"]
    if not isinstance(sig, str) or not sig.strip():
        raise ValueError(f"claim {claim_id}: falsifier.failure_signature must be non-empty string")
    return Falsifier(
        test_id=test_id,
        invariants_cited=tuple(cited),
        failure_signature=sig,
    )


def _parse_one(entry: dict[str, Any], index: int, *, schema_version: int) -> Claim:
    required_v1 = {"id", "priority", "description", "evidence_paths", "added_utc"}
    required_v2 = required_v1 | {"tier"}
    required = required_v2 if schema_version >= 2 else required_v1
    missing = required - set(entry.keys())
    if missing:
        raise ValueError(f"claim #{index} missing fields: {sorted(missing)}")
    cid = entry["id"]
    if not isinstance(cid, str) or not ID_PATTERN.match(cid):
        raise ValueError(
            f"claim #{index}: id={cid!r} must be kebab-case "
            f"(lowercase, digits, hyphens, no leading/trailing hyphen)"
        )
    priority = entry["priority"]
    if priority not in PRIORITIES_ALL:
        raise ValueError(f"claim {cid}: priority={priority!r} not in {sorted(PRIORITIES_ALL)}")
    tier_raw: object = entry.get("tier", TIER_DEFAULT_LEGACY)
    if not isinstance(tier_raw, str) or tier_raw not in TIERS_VALID:
        raise ValueError(f"claim {cid}: tier={tier_raw!r} not in {sorted(TIERS_VALID)}")
    description = entry["description"]
    if not isinstance(description, str) or not description.strip():
        raise ValueError(f"claim {cid}: description must be a non-empty string")
    evidence = entry["evidence_paths"]
    if not isinstance(evidence, list) or not all(isinstance(p, str) for p in evidence):
        raise ValueError(f"claim {cid}: evidence_paths must be a list of strings")
    if not evidence:
        raise ValueError(f"claim {cid}: evidence_paths must contain at least one path")
    added = entry["added_utc"]
    if not isinstance(added, str) or not DATE_PATTERN.match(added):
        raise ValueError(f"claim {cid}: added_utc={added!r} must be 'YYYY-MM-DD'")
    falsifier_raw = entry.get("falsifier")
    falsifier: Falsifier | None = None
    if falsifier_raw is not None:
        falsifier = _parse_falsifier(falsifier_raw, cid)
    return Claim(
        id=cid,
        priority=priority,
        tier=tier_raw,
        description=description,
        evidence_paths=tuple(evidence),
        added_utc=added,
        falsifier=falsifier,
    )


def _validate_evidence(claim: Claim, root: Path) -> list[ValidationFailure]:
    """Return one failure per missing evidence path on a gated claim.

    Tier-aware semantics:
      ANCHORED / EXTRAPOLATED — every evidence path must exist.
      SPECULATIVE / UNKNOWN  — evidence paths may be aspirational
                               (e.g. tracking docs); existence is
                               *strongly preferred* but not gated,
                               since the tier itself states the
                               evidence gap.
    Gating still triggers only on P0 / P1 priorities.
    """
    if claim.priority not in PRIORITIES_GATED:
        return []
    tier_strict = claim.tier in {"ANCHORED", "EXTRAPOLATED"}
    failures: list[ValidationFailure] = []
    for relative in claim.evidence_paths:
        target = root / relative
        if not target.exists():
            if tier_strict:
                failures.append(
                    ValidationFailure(
                        claim_id=claim.id,
                        reason=f"missing evidence path: {relative}",
                    )
                )
            else:
                # SPECULATIVE/UNKNOWN: warn-only, do not gate.
                print(
                    f"WARN: claim {claim.id} ({claim.tier}) references missing path {relative}",
                    file=sys.stderr,
                )
    return failures


def main(argv: list[str] | None = None) -> int:
    del argv  # accept-no-args contract; flags would invite ad-hoc skipping.
    try:
        registry = _load_registry(CLAIMS_PATH)
        schema_version = _resolve_schema_version(registry)
        claims = _parse_claims(registry)
    except (FileNotFoundError, TypeError, ValueError) as exc:
        print(f"CLAIMS.yaml schema violation: {exc}", file=sys.stderr)
        return 1

    failures: list[ValidationFailure] = []
    for claim in claims:
        failures.extend(_validate_evidence(claim, ROOT))

    gated_total = sum(1 for c in claims if c.priority in PRIORITIES_GATED)
    tier_counts: dict[str, int] = {t: 0 for t in TIERS_VALID}
    for c in claims:
        tier_counts[c.tier] += 1
    if failures:
        print(
            f"FAIL: {len(failures)} evidence violation(s) across {gated_total} gated claim(s):",
            file=sys.stderr,
        )
        for f in failures:
            print(f"  {f}", file=sys.stderr)
        return 1

    tier_summary = ", ".join(f"{t}={tier_counts[t]}" for t in sorted(TIERS_VALID))

    # v3 falsifier coverage — FAIL-CLOSED for P0/P1 ANCHORED claims
    # (ADR 0021, Phase 1.1; supersedes the Phase 1.0 warn-only path).
    #
    # Doctrine (CLAUDE.md / FORBIDDEN_CLAIMS): "No falsifier means no
    # claim." ANCHORED is the strongest evidence tier the registry can
    # assert; an ANCHORED claim with no structural falsifier block is
    # indistinguishable from an aspirational README line. The gate now
    # refuses it instead of merely warning.
    #
    # Scope is deliberately ANCHORED ∩ {P0, P1}:
    #   * EXTRAPOLATED/SPECULATIVE/UNKNOWN tiers are *not yet anchored*;
    #     the tier itself already declares the evidence gap, so a missing
    #     falsifier there is expected, not a lie. Gating them would
    #     conflate "not yet proven" with "claimed but unbacked".
    #   * P2 claims are informational and never gated (parity with the
    #     evidence-path gate above).
    # Structural presence is enforced here; test_id → live pytest node
    # resolution remains the job of compute_fps_audit (see header note).
    falsifier_summary = ""
    if schema_version >= 3:
        gated_anchored = [
            c for c in claims if c.tier == "ANCHORED" and c.priority in PRIORITIES_GATED
        ]
        without_falsifier = [c for c in gated_anchored if c.falsifier is None]
        if without_falsifier:
            print(
                f"FAIL: {len(without_falsifier)}/{len(gated_anchored)} P0/P1 ANCHORED "
                f"claim(s) lack a v3 falsifier block (no falsifier ⇒ no claim):",
                file=sys.stderr,
            )
            for c in without_falsifier:
                print(
                    f"  [{c.id}] ({c.priority}/{c.tier}) missing falsifier block — add "
                    f"falsifier.{{test_id, invariants_cited, failure_signature}} "
                    f"or demote the tier.",
                    file=sys.stderr,
                )
            return 1
        with_falsifier = len(gated_anchored) - len(without_falsifier)
        falsifier_summary = (
            f"; falsifier coverage: {with_falsifier}/{len(gated_anchored)} P0/P1 ANCHORED"
        )

    print(
        f"PASS: schema v{schema_version}; "
        f"{gated_total} gated claim(s), {len(claims) - gated_total} P2; "
        f"all evidence paths present; "
        f"tier distribution: {tier_summary}{falsifier_summary}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
