# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Permanent guard: governance docs must carry no unresolved merge markers.

Born from PR #692 conflict resolution which left an orphan ``<<<<<<< HEAD``
line at ``docs/governance/D002G_CANONICAL_RUN_BLOCKERS.md:254`` without a
matching ``=======`` / ``>>>>>>>``. The same defect class can recur on any
governance / research / commit-acceptor file that a future operator hand-
merges. This module scans the canonical trees for the four standard
git-merge conflict markers and fail-closes the suite on any hit.

Scanned trees:
    * ``docs/governance/`` — preregistrations, ledgers, acceptance rules
    * ``docs/research/``   — research preregistrations and reports
    * ``.claude/commit_acceptors/`` — diff-bound acceptor contracts

The scanner itself is intentionally simple (line-oriented regex) so it
matches the same anchors a human reviewer would notice. A self-test
function feeds it a temp file containing fake markers to guarantee the
scanner detects what it claims to detect (drift-sentinel).
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT: Path = Path(__file__).resolve().parents[2]

# Matches the four git-merge conflict marker line-starts:
#   ``<<<<<<<``  ``=======``  ``>>>>>>>``  ``|||||||`` (diff3-style base)
_MARKER: re.Pattern[str] = re.compile(r"^(<<<<<<<|=======|>>>>>>>|\|\|\|\|\|\|\|)")


def _scan_dir(rel: str, suffixes: tuple[str, ...]) -> list[tuple[str, int, str]]:
    """Return ``(rel_path, line_no, marker)`` for every conflict marker.

    Walks ``REPO_ROOT / rel`` recursively for files whose name ends with any
    of ``suffixes`` and reports the file (relative to ``REPO_ROOT``), the
    1-based line number, and the literal marker string. Files outside the
    UTF-8 universe are silently skipped — those are not docs/configs.
    """
    root = REPO_ROOT / rel
    hits: list[tuple[str, int, str]] = []
    if not root.exists():
        return hits
    for suffix in suffixes:
        for p in sorted(root.rglob(f"*{suffix}")):
            try:
                text = p.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for i, line in enumerate(text.splitlines(), start=1):
                m = _MARKER.match(line)
                if m:
                    rel_p = str(p.relative_to(REPO_ROOT))
                    hits.append((rel_p, i, m.group(1)))
    return hits


def _scan_file(path: Path) -> list[tuple[str, int, str]]:
    """Single-file variant of ``_scan_dir`` for the drift-sentinel test."""
    hits: list[tuple[str, int, str]] = []
    text = path.read_text(encoding="utf-8")
    for i, line in enumerate(text.splitlines(), start=1):
        m = _MARKER.match(line)
        if m:
            hits.append((str(path), i, m.group(1)))
    return hits


def test_governance_docs_have_no_unresolved_merge_markers() -> None:
    """``docs/governance/`` must be free of git-merge conflict markers.

    Scans every ``*.md``, ``*.yaml``, ``*.yml``, ``*.json`` under the
    governance tree. The orphan ``<<<<<<< HEAD`` at
    ``D002G_CANONICAL_RUN_BLOCKERS.md:254`` (introduced by PR #692
    conflict resolution) is the exact defect this guard fences.
    """
    suffixes: tuple[str, ...] = (".md", ".yaml", ".yml", ".json")
    hits = _scan_dir("docs/governance", suffixes)
    assert hits == [], "Unresolved merge marker(s) in docs/governance/:\n" + "\n".join(
        f"  {f}:{ln}: {marker!r}" for f, ln, marker in hits
    )
    # Two assertions: scanner must have actually traversed (defensive
    # check — if the directory disappears the guard silently passes).
    gov_root = REPO_ROOT / "docs" / "governance"
    msg = "docs/governance/ must exist as a dir; guard is meaningless without a scan target"
    assert gov_root.is_dir(), msg


def test_research_docs_have_no_unresolved_merge_markers() -> None:
    """``docs/research/`` must be free of git-merge conflict markers.

    Same contract as the governance guard; covers research pre-regs and
    closing reports that may be hand-merged across long-lived branches.
    """
    suffixes: tuple[str, ...] = (".md", ".yaml", ".yml", ".json")
    hits = _scan_dir("docs/research", suffixes)
    assert hits == [], "Unresolved merge marker(s) in docs/research/:\n" + "\n".join(
        f"  {f}:{ln}: {marker!r}" for f, ln, marker in hits
    )
    # Distinct second assertion: the marker regex must still recognise
    # every canonical marker — guard against accidental regex drift.
    for canonical in ("<<<<<<<", "=======", ">>>>>>>", "|||||||"):
        assert _MARKER.match(canonical) is not None, (
            f"_MARKER regex no longer recognises canonical marker {canonical!r}; "
            "scanner is silently broken"
        )


def test_commit_acceptors_have_no_unresolved_merge_markers() -> None:
    """``.claude/commit_acceptors/*.yaml`` must be free of merge markers.

    Acceptor YAMLs are diff-bound contracts; an unresolved marker would
    crash the validator with a YAML parse error and silently disarm the
    whole acceptor regime — fence it here.
    """
    suffixes: tuple[str, ...] = (".yaml", ".yml")
    hits = _scan_dir(".claude/commit_acceptors", suffixes)
    assert hits == [], "Unresolved merge marker(s) in .claude/commit_acceptors/:\n" + "\n".join(
        f"  {f}:{ln}: {marker!r}" for f, ln, marker in hits
    )
    # Distinct second assertion: acceptor dir must actually exist (else
    # the entire acceptor regime is gone and this guard is irrelevant
    # but should at least surface the structural breakage).
    assert (REPO_ROOT / ".claude" / "commit_acceptors").is_dir(), (
        ".claude/commit_acceptors/ must exist as a directory; "
        "guard is meaningless without a scan target"
    )


def test_scanner_finds_markers_when_present(tmp_path: Path) -> None:
    """Drift-sentinel: scanner must detect markers in a synthetic file.

    Writes a temp file containing all four canonical markers, runs the
    single-file scanner against it, and asserts every marker shows up
    with the correct line number. If this regresses, the directory-wide
    guards above might silently report clean while real markers slip
    through — that is exactly the failure mode this test exists to
    prevent.
    """
    f = tmp_path / "fake_conflict.md"
    f.write_text(
        "before\n"
        "<<<<<<< HEAD\n"
        "ours\n"
        "||||||| common-ancestor\n"
        "base\n"
        "=======\n"
        "theirs\n"
        ">>>>>>> branch\n"
        "after\n",
        encoding="utf-8",
    )
    hits = _scan_file(f)
    # Case 1: every canonical marker is detected.
    detected_markers = {marker for _, _, marker in hits}
    assert detected_markers == {
        "<<<<<<<",
        "|||||||",
        "=======",
        ">>>>>>>",
    }, f"Scanner failed to detect all canonical markers; got {detected_markers!r}"
    # Case 2: line numbers are 1-based and correct.
    line_by_marker = {marker: line for _, line, marker in hits}
    assert line_by_marker["<<<<<<<"] == 2
    assert line_by_marker["|||||||"] == 4
    assert line_by_marker["======="] == 6
    assert line_by_marker[">>>>>>>"] == 8
