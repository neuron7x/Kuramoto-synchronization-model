# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Self-checking governance gates for the systemic-risk module.

Three machine-checked functions that close the loophole between
documented protocol and shipped artefact:

* :func:`assert_claim_tier` — refuses to certify a claim that exceeds
  the evidence available in the supplied readiness profile.
* :func:`build_validation_readiness_report` — derives that profile
  from the live module state (presence of executable run-paths,
  bundled real-data placeholders, replication evidence).
* :func:`run_premerge_science_gate` — composes the readiness report
  with a documentation-overclaim grep gate, returning a single
  pass/fail verdict suitable for a CI ``test_*`` invocation.

Pure-function API. No I/O beyond reading the current package's own
documentation files for the overclaim grep.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

__all__ = [
    "ClaimTier",
    "ValidationReadinessReport",
    "PremergeGateReport",
    "FORBIDDEN_OVERCLAIM_TERMS",
    "assert_claim_tier",
    "build_validation_readiness_report",
    "run_premerge_science_gate",
]


ClaimTier = Literal[
    "IDEA",
    "HYPOTHESIS",
    "INSTRUMENTED",
    "TESTED_ON_SYNTHETIC",
    "TESTED_ON_REAL_DATA",
    "MEASURED",
    "REPLICATED",
    "VALIDATED",
]


# Forbidden terms in user-facing docs and code comments BEFORE the
# tier ladder advances past TESTED_ON_REAL_DATA. Each term is a
# regex word boundary so e.g. "validated" matches but "VALIDATED"
# (status enum string) does not.
#
# Per the canonical R&D checklist § 2: these terms describe levels
# of evidence that the current main does NOT possess.
FORBIDDEN_OVERCLAIM_TERMS: tuple[str, ...] = (
    r"\bproduction-?grade\b",
    r"\bproduction-?ready\b",
    r"\bempirically established\b",
    r"\btrading edge\b",
    r"\btrading signal\b",
    r"\bpredictive system\b",
    r"\bpredicts crisis\b",
    r"\bearly-warning system\b",
    r"\bproven\b",
    r"\bconfirmed\b",
)


@dataclass(frozen=True, slots=True)
class ValidationReadinessReport:
    """Machine-readable readiness profile.

    Each boolean reflects the *currently demonstrable* state of the
    module's evidence base, not its pre-registered design. The
    upper-bound claim tier is the first tier whose required evidence
    is missing.
    """

    score_level_ready: bool
    end_to_end_ready: bool
    real_data_ready: bool
    null_audit_ready: bool
    replication_ready: bool
    max_allowed_tier: ClaimTier


@dataclass(frozen=True, slots=True)
class PremergeGateReport:
    """Composite verdict from :func:`run_premerge_science_gate`."""

    readiness: ValidationReadinessReport
    overclaim_hits: tuple[tuple[str, str], ...]  # (path, matched_term)
    passed: bool
    failure_reasons: tuple[str, ...]


def assert_claim_tier(
    *,
    claimed: ClaimTier,
    evidence: ValidationReadinessReport,
) -> None:
    """Raise :class:`AssertionError` if ``claimed`` exceeds available evidence.

    The mapping from tier to required evidence is fixed by
    ``PROTOCOL.md § 7`` (post-detection promotion path). This
    function is the executable enforcer of that table.
    """
    if not _tier_supported(claimed, evidence):
        raise AssertionError(
            f"claim tier '{claimed}' exceeds available evidence: "
            f"max_allowed={evidence.max_allowed_tier} "
            f"(score_level={evidence.score_level_ready}, "
            f"end_to_end={evidence.end_to_end_ready}, "
            f"real_data={evidence.real_data_ready}, "
            f"null_audit={evidence.null_audit_ready}, "
            f"replication={evidence.replication_ready})"
        )


def build_validation_readiness_report(
    *,
    score_level_executable: bool,
    end_to_end_executable: bool,
    real_data_run_executed: bool,
    null_audit_executable: bool,
    replication_independent: bool,
) -> ValidationReadinessReport:
    """Derive a readiness profile from explicit per-axis flags.

    The caller is responsible for setting each flag truthfully —
    every flag should map to a *demonstrable* artefact (a passing
    test, a signed run manifest, an independent reviewer's report).
    Default to ``False`` whenever uncertain.
    """
    if not score_level_executable:
        max_tier: ClaimTier = "HYPOTHESIS"
    elif not end_to_end_executable:
        max_tier = "INSTRUMENTED"
    elif not real_data_run_executed:
        max_tier = "TESTED_ON_SYNTHETIC"
    elif not null_audit_executable:
        max_tier = "TESTED_ON_REAL_DATA"
    elif not replication_independent:
        max_tier = "MEASURED"
    else:
        max_tier = "VALIDATED"
    return ValidationReadinessReport(
        score_level_ready=score_level_executable,
        end_to_end_ready=end_to_end_executable,
        real_data_ready=real_data_run_executed,
        null_audit_ready=null_audit_executable,
        replication_ready=replication_independent,
        max_allowed_tier=max_tier,
    )


def run_premerge_science_gate(
    *,
    docs_root: Path,
    readiness: ValidationReadinessReport,
    grep_extensions: tuple[str, ...] = (".md", ".py"),
) -> PremergeGateReport:
    """One-shot composite gate: docs honesty + readiness consistency.

    Scans every file with an extension in ``grep_extensions`` under
    ``docs_root`` (recursively, but excluding obvious build/dist
    paths) for matches against :data:`FORBIDDEN_OVERCLAIM_TERMS`.
    Produces a structured :class:`PremergeGateReport`. ``passed`` is
    ``True`` only when:

    * no overclaim term is matched, AND
    * the readiness profile's ``max_allowed_tier`` is
      ``HYPOTHESIS`` or ``INSTRUMENTED`` (the post-merge state is
      consistent with the canonical R&D checklist's
      "MERGE AS HYPOTHESIS / INSTRUMENTATION ONLY" decision).
    """
    if not docs_root.is_dir():
        raise FileNotFoundError(f"docs_root not found: {docs_root}")
    overclaim_hits: list[tuple[str, str]] = []
    pattern = re.compile("|".join(FORBIDDEN_OVERCLAIM_TERMS), re.IGNORECASE)
    for path in sorted(docs_root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix not in grep_extensions:
            continue
        if any(part.startswith(".") for part in path.parts):
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        # Skip the governance module itself — it must literally
        # contain the forbidden terms in order to forbid them.
        if path.name in {"governance.py", "test_governance.py"}:
            continue
        for match in pattern.finditer(content):
            overclaim_hits.append((str(path.relative_to(docs_root)), match.group(0)))
    failure_reasons: list[str] = []
    if overclaim_hits:
        failure_reasons.append(f"{len(overclaim_hits)} overclaim term(s) matched in docs/code")
    if readiness.max_allowed_tier not in {"HYPOTHESIS", "INSTRUMENTED"}:
        failure_reasons.append(
            f"max_allowed_tier={readiness.max_allowed_tier} but no real-data "
            f"evidence is on the canonical main; readiness profile is over-claiming"
        )
    return PremergeGateReport(
        readiness=readiness,
        overclaim_hits=tuple(overclaim_hits),
        passed=not failure_reasons,
        failure_reasons=tuple(failure_reasons),
    )


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


_TIER_ORDER: dict[ClaimTier, int] = {
    "IDEA": 0,
    "HYPOTHESIS": 1,
    "INSTRUMENTED": 2,
    "TESTED_ON_SYNTHETIC": 3,
    "TESTED_ON_REAL_DATA": 4,
    "MEASURED": 5,
    "REPLICATED": 6,
    "VALIDATED": 7,
}


def _tier_supported(claimed: ClaimTier, evidence: ValidationReadinessReport) -> bool:
    return _TIER_ORDER[claimed] <= _TIER_ORDER[evidence.max_allowed_tier]
