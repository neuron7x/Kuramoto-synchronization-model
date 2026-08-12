#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Automated First-Principles Score (FPS_audit) computation.

Per IERD-PAI-FPS-UX-001 §5:

    FPS_audit = (claims with evidence_test_id) / (total FPS claims)

Operationally, "with evidence_test_id" means: for tier ANCHORED or
EXTRAPOLATED, every path in ``evidence_paths`` exists AND at least
one path is a test file (``tests/...``) or a frozen artefact (under
``results/``, ``paper/``, ``research/``, ``docs/validation/``,
``docs/reports/``, ``docs/audit/``). SPECULATIVE and UNKNOWN are
counted but never contribute to the numerator.

Outputs:

    docs/validation/fps_audit_latest.json — machine-readable snapshot
    stdout                                 — human-readable summary

Exit codes:

    0  FPS_audit ≥ threshold (default 1.00 from IERD §5).
    1  FPS_audit < threshold OR registry parse failure.

Run locally before push:

    python scripts/ci/compute_fps_audit.py
    python scripts/ci/compute_fps_audit.py --threshold 0.95
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CLAIMS_PATH = ROOT / "docs" / "CLAIMS.yaml"
OUTPUT_PATH = ROOT / "docs" / "validation" / "fps_audit_latest.json"
DEFAULT_THRESHOLD = 1.00

ANCHORED_TIERS = frozenset({"ANCHORED", "EXTRAPOLATED"})
ALL_TIERS = frozenset({"ANCHORED", "EXTRAPOLATED", "SPECULATIVE", "UNKNOWN"})

EVIDENCE_PATH_PREFIXES_FOR_TEST: tuple[str, ...] = ("tests/",)
EVIDENCE_PATH_PREFIXES_FOR_ARTEFACT: tuple[str, ...] = (
    "results/",
    "paper/",
    "research/",
    "docs/validation/",
    "docs/reports/",
    "docs/audit/",
    "docs/laws/",
    "docs/governance/",  # binding directives count as governance artefacts
    "docs/adr/",  # ADRs count as decision artefacts
)


@dataclass(frozen=True)
class ClaimRow:
    cid: str
    priority: str
    tier: str
    evidence_paths: tuple[str, ...]


@dataclass(frozen=True)
class ClaimAudit:
    claim: ClaimRow
    has_test: bool
    has_artefact: bool
    all_paths_exist: bool
    counts_for_numerator: bool
    missing_paths: tuple[str, ...]


@dataclass
class FpsSnapshot:
    fps_audit: float
    threshold: float
    threshold_met: bool
    total_anchored_or_extrapolated: int
    qualifying: int
    tier_distribution: dict[str, int]
    audits: list[ClaimAudit]

    def to_dict(self) -> dict[str, object]:
        return {
            "fps_audit": self.fps_audit,
            "threshold": self.threshold,
            "threshold_met": self.threshold_met,
            "total_anchored_or_extrapolated": self.total_anchored_or_extrapolated,
            "qualifying": self.qualifying,
            "tier_distribution": dict(self.tier_distribution),
            "audits": [
                {
                    "id": a.claim.cid,
                    "tier": a.claim.tier,
                    "priority": a.claim.priority,
                    "has_test_evidence": a.has_test,
                    "has_artefact_evidence": a.has_artefact,
                    "all_paths_exist": a.all_paths_exist,
                    "counts_for_numerator": a.counts_for_numerator,
                    "missing_paths": list(a.missing_paths),
                }
                for a in self.audits
            ],
        }


def _load_claims() -> list[ClaimRow]:
    raw = yaml.safe_load(CLAIMS_PATH.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("CLAIMS.yaml must be a YAML mapping at the top level")
    schema = raw.get("schema_version")
    if schema not in (1, 2, 3):
        raise ValueError(f"unsupported schema_version={schema!r}")
    entries = raw.get("claims") or []
    rows: list[ClaimRow] = []
    for entry in entries:
        cid = entry.get("id", "")
        priority = entry.get("priority", "")
        tier = entry.get("tier", "ANCHORED" if schema == 1 else "")
        if tier not in ALL_TIERS:
            raise ValueError(f"claim {cid!r}: tier={tier!r} not in {sorted(ALL_TIERS)}")
        evidence = entry.get("evidence_paths") or []
        rows.append(
            ClaimRow(
                cid=cid,
                priority=priority,
                tier=tier,
                evidence_paths=tuple(evidence),
            )
        )
    return rows


def _audit_claim(row: ClaimRow) -> ClaimAudit:
    has_test = any(p.startswith(EVIDENCE_PATH_PREFIXES_FOR_TEST) for p in row.evidence_paths)
    has_artefact = any(
        p.startswith(EVIDENCE_PATH_PREFIXES_FOR_ARTEFACT) for p in row.evidence_paths
    )
    missing = tuple(p for p in row.evidence_paths if not (ROOT / p).exists())
    all_paths_exist = not missing
    counts = row.tier in ANCHORED_TIERS and all_paths_exist and (has_test or has_artefact)
    return ClaimAudit(
        claim=row,
        has_test=has_test,
        has_artefact=has_artefact,
        all_paths_exist=all_paths_exist,
        counts_for_numerator=counts,
        missing_paths=missing,
    )


def compute_fps_audit(threshold: float = DEFAULT_THRESHOLD) -> FpsSnapshot:
    rows = _load_claims()
    audits = [_audit_claim(r) for r in rows]
    tier_dist: dict[str, int] = {t: 0 for t in ALL_TIERS}
    for r in rows:
        tier_dist[r.tier] += 1
    denom = sum(tier_dist[t] for t in ANCHORED_TIERS)
    qualifying = sum(1 for a in audits if a.counts_for_numerator)
    fps = qualifying / denom if denom else 0.0
    return FpsSnapshot(
        fps_audit=fps,
        threshold=threshold,
        threshold_met=fps >= threshold,
        total_anchored_or_extrapolated=denom,
        qualifying=qualifying,
        tier_distribution=tier_dist,
        audits=audits,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compute First-Principles Score per IERD-PAI-FPS-UX-001 §5."
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_THRESHOLD,
        help="Pass/fail threshold (default 1.00 from IERD §5).",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write the snapshot to docs/validation/fps_audit_latest.json.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress per-claim output; print only the verdict line.",
    )
    args = parser.parse_args(argv)

    try:
        snapshot = compute_fps_audit(threshold=args.threshold)
    except (FileNotFoundError, ValueError) as exc:
        print(f"compute_fps_audit: {exc}", file=sys.stderr)
        return 1

    if args.write:
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_PATH.write_text(
            json.dumps(snapshot.to_dict(), indent=2) + "\n",
            encoding="utf-8",
        )

    if not args.quiet:
        for audit in snapshot.audits:
            mark = "PASS" if audit.counts_for_numerator else "----"
            test_flag = "T" if audit.has_test else "-"
            artefact_flag = "A" if audit.has_artefact else "-"
            paths_flag = "p" if audit.all_paths_exist else "M"
            print(
                f"  [{mark}] [{test_flag}{artefact_flag}{paths_flag}] "
                f"{audit.claim.tier:13s} {audit.claim.cid}"
            )

    tier_summary = ", ".join(f"{t}={snapshot.tier_distribution[t]}" for t in sorted(ALL_TIERS))
    verdict = "PASS" if snapshot.threshold_met else "FAIL"
    print(
        f"{verdict}: FPS_audit = {snapshot.qualifying}/{snapshot.total_anchored_or_extrapolated} = "
        f"{snapshot.fps_audit:.4f} (threshold {snapshot.threshold}); "
        f"tiers: {tier_summary}"
    )
    return 0 if snapshot.threshold_met else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
