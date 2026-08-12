#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Semantic truth gate for research artifacts (second-layer hardening).

The JSON schema (``schemas/research/research_inference_artifact.schema.json``)
proves *shape*: that an artifact has the right fields of the right types. It
cannot prove *truth*: a hand-typed ``score`` of 0.742 with an all-zero data hash
and ``falsification_status: PASS`` is schema-valid and a lie.

This gate closes that gap. It encodes the semantic contract that a schema
cannot: an artifact may not simultaneously claim evidence (``PASS``) and carry
the fingerprints of having no data (zero hashes, placeholder score, HYPOTHESIS
tier). Conversely, a zero-data artifact must label itself honestly (NOT_RUN /
BLOCKED, OBSERVE / REJECT) and be explicitly marked a placeholder.

Run::

    python scripts/ci/check_research_artifact_truth.py

Exit codes::

    0  — every research artifact is semantically honest
    1  — at least one artifact is schema-valid but semantically fake
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

# Directories whose JSON files are treated as research artifacts.
SCAN_ROOTS: tuple[str, ...] = ("artifacts/runs", "research_lines")

ZERO_SHA256 = "0" * 64
ZERO_SHA1_GIT = "0" * 40

# Canonical fields that mark a JSON document as a research inference artifact.
# A file is only judged by this gate if it carries the evidence-bearing core.
ARTIFACT_MARKER_FIELDS: frozenset[str] = frozenset(
    {"data_sha256", "falsification_status", "claim_tier"}
)

# Tiers that assert empirical measurement; never compatible with zero data.
EVIDENCE_TIERS: frozenset[str] = frozenset(
    {"MEASURED_SINGLE", "MEASURED_MULTI", "LIMITED_EMPIRICAL"}
)

# Decisions admissible for a non-evidence (zero-data) artifact.
NON_EVIDENCE_DECISIONS: frozenset[str] = frozenset({"OBSERVE", "REJECT"})

# Known placeholder score constants that must never accompany a PASS.
PLACEHOLDER_SCORES: frozenset[float] = frozenset({0.0, 0.742})


def is_artifact(doc: Any) -> bool:
    """Return True iff *doc* looks like a research inference artifact."""
    return isinstance(doc, Mapping) and ARTIFACT_MARKER_FIELDS.issubset(doc.keys())


def is_placeholder(path: Path, doc: Mapping[str, Any]) -> bool:
    """Placeholder iff the filename says so or ``artifact_role == placeholder``."""
    if "placeholder" in path.name.lower():
        return True
    return doc.get("artifact_role") == "placeholder"


def _has_reproducible_lineage(doc: Mapping[str, Any]) -> bool:
    """Minimal lineage to reproduce a run: non-zero data + config + git + seed."""
    return (
        doc.get("data_sha256") not in (None, "", ZERO_SHA256)
        and doc.get("config_sha256") not in (None, "", ZERO_SHA256)
        and doc.get("git_sha") not in (None, "", ZERO_SHA1_GIT)
        and isinstance(doc.get("seed"), int)
    )


def evaluate_artifact(path: Path, doc: Mapping[str, Any]) -> list[str]:
    """Return a list of semantic-truth violations for one artifact (empty == OK)."""
    errors: list[str] = []
    rel = path.as_posix()

    data_sha = doc.get("data_sha256")
    git_sha = doc.get("git_sha")
    status = doc.get("falsification_status")
    tier = doc.get("claim_tier")
    decision = doc.get("decision")
    score = doc.get("score")
    placeholder = is_placeholder(path, doc)

    zero_data = data_sha in (None, "", ZERO_SHA256)
    zero_git = git_sha in (None, "", ZERO_SHA1_GIT)

    score_source = doc.get("score_source")
    replay_command = doc.get("replay_command")
    baseline = doc.get("baseline")

    # Rule 1 — a PASS is a claim of evidence and must be backed by real lineage:
    # real hashes, a pinned method, a computed score, a baseline it was judged
    # against, and a command that reproduces it. A claim you cannot replay or
    # falsify is not evidence.
    if status == "PASS":
        if zero_data:
            errors.append(f"{rel}: falsification_status=PASS with zero data_sha256")
        if zero_git:
            errors.append(f"{rel}: falsification_status=PASS with zero git_sha")
        if tier == "HYPOTHESIS":
            errors.append(f"{rel}: falsification_status=PASS with claim_tier=HYPOTHESIS")
        if isinstance(score, (int, float)) and float(score) in PLACEHOLDER_SCORES:
            errors.append(f"{rel}: falsification_status=PASS with placeholder score={score}")
        if not _has_reproducible_lineage(doc):
            errors.append(f"{rel}: falsification_status=PASS without reproducible lineage")
        if score_source != "computed":
            errors.append(
                f"{rel}: falsification_status=PASS requires score_source=computed, "
                f"got {score_source!r}"
            )
        if not (isinstance(replay_command, str) and replay_command.strip()):
            errors.append(f"{rel}: falsification_status=PASS requires a non-empty replay_command")
        if not (isinstance(baseline, str) and baseline.strip()):
            errors.append(
                f"{rel}: falsification_status=PASS requires a baseline "
                "(a result with no null/baseline is asserted, not falsified)"
            )
        # Evidence-grade lineage (SLSA resolvedDependencies / ACM Results-Reproduced
        # / PROV wasAttributedTo): a PASS must pin its environment, fix the exact
        # output it reproduces, and name the responsible agent — otherwise "replay"
        # proves nothing across machines and the claim has no owner.
        env_sha256 = doc.get("env_sha256")
        output_sha256 = doc.get("output_sha256")
        agent = doc.get("agent")
        if env_sha256 in (None, "", ZERO_SHA256):
            errors.append(
                f"{rel}: falsification_status=PASS requires a non-zero env_sha256 "
                "(pinned dependency/BLAS closure; replay is not portable without it)"
            )
        if output_sha256 in (None, "", ZERO_SHA256):
            errors.append(
                f"{rel}: falsification_status=PASS requires output_sha256 "
                "(verifies reproduction of the result, not mere re-execution)"
            )
        if not (isinstance(agent, str) and agent.strip()):
            errors.append(
                f"{rel}: falsification_status=PASS requires an agent attribution "
                "(ci:<workflow>@<sha> | local:<host> | human:<id>)"
            )

    # Rule 2 — zero data hash means no run happened; it must say so honestly.
    if zero_data:
        if status not in ("NOT_RUN", "BLOCKED"):
            errors.append(
                f"{rel}: zero data_sha256 requires falsification_status in "
                f"{{NOT_RUN, BLOCKED}}, got {status!r}"
            )
        if decision is not None and decision not in NON_EVIDENCE_DECISIONS:
            errors.append(
                f"{rel}: zero data_sha256 requires decision in "
                f"{{OBSERVE, REJECT}}, got {decision!r}"
            )
        if tier in EVIDENCE_TIERS:
            errors.append(f"{rel}: zero data_sha256 cannot carry empirical claim_tier {tier!r}")

    # Rule 3 — zero git SHA means the run is not attributable, so not evidence.
    if zero_git and status == "PASS":
        errors.append(f"{rel}: zero git_sha cannot be evidence-bearing (PASS)")

    # Rule 4 — a placeholder must never masquerade as a passing result.
    if placeholder and status == "PASS":
        errors.append(f"{rel}: artifact marked placeholder but falsification_status=PASS")

    # Rule 5 — a non-placeholder artifact with zero data is a latent lie waiting to
    # be promoted; require the explicit placeholder marker so intent is on record.
    if zero_data and not placeholder:
        errors.append(
            f"{rel}: zero-data artifact must be explicitly marked placeholder "
            "(filename '*placeholder*' or field artifact_role: placeholder)"
        )

    # Rule 6 — score provenance must match reality: an artifact that ran nothing
    # (NOT_RUN) or is a placeholder cannot claim its score was computed.
    if score_source == "computed" and (status == "NOT_RUN" or placeholder):
        errors.append(
            f"{rel}: score_source=computed contradicts "
            f"{'placeholder role' if placeholder else 'falsification_status=NOT_RUN'}"
        )

    # Rule 7 — NOT_APPLICABLE is the honest status for a real score computed on
    # NON-empirical inputs (synthetic / instrumented plumbing): a number was
    # produced, but no falsification or evidence is claimed. It must say exactly
    # that and nothing more — never an empirical tier, always a computed score.
    # (Real-data requirement is enforced by Rule 2: zero data forces NOT_RUN/
    # BLOCKED, so a NOT_APPLICABLE artifact cannot have a zero data hash.)
    if status == "NOT_APPLICABLE":
        if tier in EVIDENCE_TIERS:
            errors.append(
                f"{rel}: falsification_status=NOT_APPLICABLE cannot carry empirical "
                f"claim_tier {tier!r} — a computed-but-unfalsified result is not evidence"
            )
        if score_source != "computed":
            errors.append(
                f"{rel}: falsification_status=NOT_APPLICABLE requires score_source=computed "
                f"(it marks a computed, non-evidence result), got {score_source!r}"
            )

    # Rule 8 — tier↔status compatibility matrix: a terminal/instrumented tier must
    # carry a status consistent with its meaning, so the two cannot contradict
    # (PROV-DM §5.6 qualified-relation completeness; FAIR R1.2 self-consistency).
    tier_status_ok: dict[str, frozenset[str]] = {
        "REJECTED": frozenset({"FAIL", "NOT_APPLICABLE"}),
        "BLOCKED_COST_MODEL": frozenset({"BLOCKED"}),
        "INSTRUMENTED": frozenset({"NOT_APPLICABLE", "NOT_RUN"}),
    }
    allowed = tier_status_ok.get(tier) if isinstance(tier, str) else None
    if allowed is not None and status not in allowed:
        errors.append(
            f"{rel}: claim_tier={tier!r} is incompatible with "
            f"falsification_status={status!r} (expected one of {sorted(allowed)})"
        )

    return errors


def iter_artifact_files(repo_root: Path, roots: Iterable[str]) -> list[Path]:
    """Collect candidate JSON files under the scan roots."""
    found: list[Path] = []
    for root in roots:
        base = repo_root / root
        if not base.exists():
            continue
        found.extend(sorted(base.rglob("*.json")))
    return found


def check(repo_root: Path, roots: Iterable[str] = SCAN_ROOTS) -> list[str]:
    """Evaluate every research artifact under *roots*; return all violations."""
    violations: list[str] = []
    for path in iter_artifact_files(repo_root, roots):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:  # malformed JSON is its own gate
            violations.append(f"{path.as_posix()}: unreadable JSON ({exc})")
            continue
        if not is_artifact(doc):
            continue
        violations.extend(evaluate_artifact(path.relative_to(repo_root), doc))
    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="Repository root (defaults to the repo containing this script).",
    )
    args = parser.parse_args(argv)

    violations = check(args.repo_root)
    if violations:
        print("Research-artifact truth gate FAILED:", file=sys.stderr)
        for v in violations:
            print(f"  ✗ {v}", file=sys.stderr)
        print(
            f"\n{len(violations)} semantic violation(s). Schema-valid does not mean true.",
            file=sys.stderr,
        )
        return 1
    print("Research-artifact truth gate passed: all artifacts semantically honest.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
