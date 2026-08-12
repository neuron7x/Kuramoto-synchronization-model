#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""D-002H Gate D — forbidden-claim scanner.

Walks the D-002H governance / artifact / acceptor / test surface and
records every line that contains a forbidden phrase from the locked
D-002H pre-registration ``forbidden_claims`` list (sha256
``44b18b5a40ce9d188a9c3bd49339621f81a65a15f97a683247902450dd54acec``).

A line is a **leak** iff:

* the line contains a forbidden phrase (case-insensitive substring), AND
* neither the line itself nor any line in the symmetric context
  window (``CONTEXT_LINES_BEFORE`` lines above, ``CONTEXT_LINES_AFTER``
  lines below) contains any of ``ALLOWED_DENIAL_MARKERS``.

The window is asymmetric because denial framing in this corpus is
typically introduced by a heading or list header above the bulleted
phrase (e.g. ``NO null-domain admissibility verdict may promote to:``
followed by a bulleted ``* D-002C rescue claim.``). A small forward
window catches inline trailing denials such as
``D-002C rescue   <- this is the forbidden phrase, not a claim``.

Files in :data:`SCANNER_EXEMPT_PATHS` are skipped: these files
intentionally enumerate the forbidden phrases as guard literals (the
scanner itself, the prereg ``forbidden_claims`` list, the
claim-boundary doc with its ``❌`` forbidden-interpretation block, etc.)
and would dominate the leak count with self-references.

Gate D contract per
``docs/governance/D002H_CANONICAL_RUN_AUTHORIZATION_GATES.md`` §D:

    Gate D PASS iff zero leaks outside the denial context across the
    scanned surface.

PASS of Gate D **alone does NOT authorise the canonical D-002H run**;
the conjunction A ∧ B ∧ C ∧ D ∧ E ∧ F ∧ G is the authorisation
contract.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[1]

ARTIFACT_RELPATH: Final[str] = "artifacts/d002h/scans/d002h_forbidden_claim_scan.json"
ARTIFACT_PATH: Final[Path] = REPO_ROOT / ARTIFACT_RELPATH

SCHEMA_VERSION: Final[str] = "D002H-GATE-D-v1"

# The forbidden_claims list from the locked D-002H prereg, plus the two
# bonus phrases per §D of the gates doc ("canonical run authorised /
# authorized" — only allowed in §gates docs as the artifact-to-be-created
# reference, never as a present-state claim).
FORBIDDEN_CLAIMS: Final[tuple[str, ...]] = (
    "cross-substrate robustness",
    "general topology robustness",
    "D-002G rescue",
    "D-002C rescue",
    "global systemic-risk conclusion",
    "scientific PASS before canonical run",
    "M4 inside D-002G",
    "block_structured remains in scope",
    "temporal_coupling remains in scope",
    "canonical run authorized",
    "canonical run authorised",
)

# Denial-marker tokens. Any occurrence (case-insensitive) within the
# context window of a forbidden-phrase hit demotes the hit from leak to
# permitted denial framing.
ALLOWED_DENIAL_MARKERS: Final[tuple[str, ...]] = (
    "❌",
    "does not",
    "do not",
    "NOT ",
    " not ",
    "MUST NOT",
    "must not",
    "forbidden",
    "FORBIDDEN",
    "out of scope",
    "excluded",
    "EXCLUDED",
    "cannot",
    "Cannot",
    "no_",
    "never",
    "Never",
    "NEVER",
    "absent",
    "rejects",
    "rejected",
    "REJECT",
    "fail-closed",
    "FAIL",
    "denied",
    "deny",
    "prohibited",
    "disallowed",
    "impossible",
    "blocked",
    "BLOCKED",
    "after explicit authorisation",
    "after all 7 gates",
    "requires explicit",
    "requires_explicit",
    "NO ",  # list-header pattern ("NO null-domain ... may promote to:")
    "no canonical",
    "no_canonical",
    "remain open",
    "remains open",
    "remain BLOCKED",
    "alone does NOT",
    "alone is one term",
)

# Asymmetric context window (lines).
CONTEXT_LINES_BEFORE: Final[int] = 8
CONTEXT_LINES_AFTER: Final[int] = 2

# Globs the scanner walks.
SCAN_GLOBS: Final[tuple[str, ...]] = (
    "docs/governance/D002*.md",
    "docs/governance/D002*.yaml",
    "artifacts/d002g/**/*",
    "artifacts/d002h/**/*",
    ".claude/commit_acceptors/x10r-d002*.yaml",
    "tests/systemic_risk/test_d002*.py",
    "scripts/x10r_d002*.py",
)

# Files exempt from scanning. Each of these BY DESIGN enumerates the
# forbidden phrases (the scanner itself, the prereg list source, the
# claim-boundary doc's ❌ block, denial-only adversarial test files,
# the acceptors that pin forbidden phrases as falsifier guards).
SCANNER_EXEMPT_PATHS: Final[frozenset[str]] = frozenset(
    {
        # The scanner itself + its tests.
        "scripts/x10r_d002h_gate_d_scan.py",
        "tests/systemic_risk/test_d002h_gate_d_forbidden_claims.py",
        # The scanner's own output artifact (it embeds the forbidden_claims
        # and allowed_denial_markers lists verbatim for audit reproducibility).
        "artifacts/d002h/scans/d002h_forbidden_claim_scan.json",
        # This PR's own report.
        "docs/governance/D002H_GATE_D_FORBIDDEN_CLAIM_SCAN.md",
        # Forbidden-claims list source.
        "docs/governance/D002H_PREREGISTRATION.yaml",
        # D-002I pre-registration enumerates the same forbidden_claims
        # list inside its denial block (it inherits the D-002H forbidden
        # set + adds D-002I-specific denials). Exempt by design,
        # mirroring D002H_PREREGISTRATION.yaml.
        "docs/governance/D002I_PREREGISTRATION.yaml",
        "docs/governance/D002I_CLAIM_BOUNDARY.md",
        "docs/governance/D002I_INVESTIGATION_RATIONALE.md",
        # ❌-block / scope-rationale docs that enumerate forbidden phrases
        # as ❌ list entries.
        "docs/governance/D002H_CLAIM_BOUNDARY.md",
        "docs/governance/D002H_CANONICAL_RUN_AUTHORIZATION_GATES.md",
        "docs/governance/D002H_SCOPE_RATIONALE.md",
        # Prior commit acceptors that contain forbidden phrases as
        # falsifier-guard literals (see falsifier ``grep -vE`` blocks).
        ".claude/commit_acceptors/x10r-d002g-nondegenerate-null-redesign.yaml",
        ".claude/commit_acceptors/x10r-d002g-p1-implementation.yaml",
        ".claude/commit_acceptors/x10r-d002g-p1-strike-scaffolding.yaml",
        ".claude/commit_acceptors/x10r-d002g-p2-m2-topology-preserving-shuffle.yaml",
        ".claude/commit_acceptors/x10r-d002g-p3-constant-payload-null-recovery.yaml",
        ".claude/commit_acceptors/x10r-d002g-m3-topology-conditioned-null.yaml",
        ".claude/commit_acceptors/x10r-d002g-structural-closure.yaml",
        ".claude/commit_acceptors/x10r-d002h-ricci-flow-prereg.yaml",
        ".claude/commit_acceptors/x10r-d002h-gate-b-eligibility.yaml",
        ".claude/commit_acceptors/x10r-d002h-gate-c-canonical-grid.yaml",
        ".claude/commit_acceptors/x10r-d002h-gate-d-forbidden-claim-scan.yaml",
        # Prior adversarial / no-promotion / no-canonical-promotion tests
        # — they intentionally pin the phrases for guard scanning.
        "tests/systemic_risk/test_d002g_m3_traps.py",
        "tests/systemic_risk/test_d002g_m3_no_promotion.py",
        "tests/systemic_risk/test_d002g_p3_traps.py",
        "tests/systemic_risk/test_d002g_p3_no_canonical_promotion.py",
        "tests/systemic_risk/test_d002g_structural_closure.py",
        "tests/systemic_risk/test_d002h_gate_b_eligibility.py",
        "tests/systemic_risk/test_d002h_preregistration.py",
        # The R2-B inapplicability test enumerates the forbidden phrases
        # verbatim as a `_FORBIDDEN_*` tuple, mirroring the Gate D scanner's
        # own exempt-by-design pattern. The note doc + tests pin the
        # phrases so they cannot drift; the test itself is therefore a
        # guard-literal-bearing file, not a leak.
        "tests/systemic_risk/test_d002h_r2b_inapplicability.py",
    }
)


# ---------------------------------------------------------------------------
# Data shapes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LeakRecord:
    """A single forbidden-phrase hit outside the denial context.

    Attributes
    ----------
    relpath:
        Repository-relative POSIX path of the leaking file.
    line_no:
        1-indexed line number of the hit.
    phrase:
        The forbidden phrase that triggered the hit (verbatim from
        :data:`FORBIDDEN_CLAIMS`).
    line:
        The line content, trimmed of the trailing newline.
    """

    relpath: str
    line_no: int
    phrase: str
    line: str

    def to_dict(self) -> dict[str, object]:
        return {
            "relpath": self.relpath,
            "line_no": self.line_no,
            "phrase": self.phrase,
            "line": self.line,
        }


@dataclass(frozen=True)
class ScanResult:
    """Aggregate verdict over the scanned surface."""

    scanned_files: tuple[str, ...]
    exempt_files: tuple[str, ...]
    leaks: tuple[LeakRecord, ...]

    @property
    def verdict(self) -> str:
        return "PASS" if not self.leaks else "FAIL"

    @property
    def files_with_leaks(self) -> tuple[str, ...]:
        seen: list[str] = []
        for leak in self.leaks:
            if leak.relpath not in seen:
                seen.append(leak.relpath)
        return tuple(seen)


# ---------------------------------------------------------------------------
# Core scanner
# ---------------------------------------------------------------------------


def _has_denial_marker(window_text: str) -> bool:
    """Return True iff any denial marker token appears in the window."""
    lowered = window_text.lower()
    for marker in ALLOWED_DENIAL_MARKERS:
        if marker.lower() in lowered:
            return True
    return False


def _scan_file(path: Path, relpath: str) -> list[LeakRecord]:
    """Scan a single file. Return the list of leaks (possibly empty)."""
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        # Binary or non-UTF8 — out of scope.
        return []
    except OSError:
        return []
    lines = text.splitlines()
    leaks: list[LeakRecord] = []
    for idx, line in enumerate(lines):
        lowered = line.lower()
        for phrase in FORBIDDEN_CLAIMS:
            if phrase.lower() not in lowered:
                continue
            lo = max(0, idx - CONTEXT_LINES_BEFORE)
            hi = min(len(lines), idx + CONTEXT_LINES_AFTER + 1)
            window = "\n".join(lines[lo:hi])
            if _has_denial_marker(window):
                continue
            leaks.append(
                LeakRecord(
                    relpath=relpath,
                    line_no=idx + 1,
                    phrase=phrase,
                    line=line.rstrip(),
                )
            )
    return leaks


def _collect_scan_paths() -> list[Path]:
    """Resolve all globs to a deduplicated sorted file list."""
    collected: set[Path] = set()
    for glob in SCAN_GLOBS:
        for hit in REPO_ROOT.glob(glob):
            if hit.is_file():
                collected.add(hit.resolve())
    return sorted(collected)


def run_scan() -> ScanResult:
    """Execute the Gate D scan. Pure function, no side effects."""
    candidates = _collect_scan_paths()
    scanned: list[str] = []
    exempt: list[str] = []
    leaks: list[LeakRecord] = []
    for abspath in candidates:
        try:
            relpath = abspath.relative_to(REPO_ROOT).as_posix()
        except ValueError:
            continue
        if relpath in SCANNER_EXEMPT_PATHS:
            exempt.append(relpath)
            continue
        scanned.append(relpath)
        leaks.extend(_scan_file(abspath, relpath))
    return ScanResult(
        scanned_files=tuple(sorted(scanned)),
        exempt_files=tuple(sorted(exempt)),
        leaks=tuple(leaks),
    )


# ---------------------------------------------------------------------------
# Artifact emission
# ---------------------------------------------------------------------------


def _result_to_artifact(result: ScanResult) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "study_id": "D-002H",
        "gate": "D",
        "scanned_files_count": len(result.scanned_files),
        "exempt_files_count": len(result.exempt_files),
        "scanned_files": list(result.scanned_files),
        "exempt_files": list(result.exempt_files),
        "forbidden_phrases": list(FORBIDDEN_CLAIMS),
        "allowed_denial_markers": list(ALLOWED_DENIAL_MARKERS),
        "context_lines_before": CONTEXT_LINES_BEFORE,
        "context_lines_after": CONTEXT_LINES_AFTER,
        "files_with_leaks": list(result.files_with_leaks),
        "leaks": [leak.to_dict() for leak in result.leaks],
        "n_leaks": len(result.leaks),
        "gate_d_verdict": result.verdict,
        "canonical_run_authorized": False,
        "downstream_gates_remaining": ["E", "F", "G"],
        "parent_prereg_sha": (
            "44b18b5a40ce9d188a9c3bd49339621f81a65a1"  # pragma: allowlist secret
            "5f97a683247902450dd54acec"
        ),
        "claim_boundary": (
            "Gate D verifies the scoped no-promotion property of D-002H "
            "docs/artifacts. PASS does NOT authorise canonical run. "
            "Conjunction A AND B AND C AND D AND E AND F AND G is the contract."
        ),
    }


def emit_artifact(result: ScanResult | None = None) -> Path:
    """Run scan (or accept a pre-computed result) and write the JSON."""
    if result is None:
        result = run_scan()
    payload = _result_to_artifact(result)
    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT_PATH.write_text(
        json.dumps(payload, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    return ARTIFACT_PATH


def main() -> int:
    result = run_scan()
    emit_artifact(result)
    if result.verdict != "PASS":
        for leak in result.leaks:
            print(f"LEAK {leak.relpath}:{leak.line_no} :: {leak.phrase!r} :: {leak.line}")
        return 12
    print(
        f"Gate D PASS: scanned={len(result.scanned_files)} "
        f"exempt={len(result.exempt_files)} leaks=0"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry
    raise SystemExit(main())
