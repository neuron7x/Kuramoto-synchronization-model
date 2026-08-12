# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Advisory fake-closure scanner.

Detects PR-body closure claims (``Closes #N`` / ``Fixes #N`` / ``Resolves #N``)
that reference an issue still carrying *unsatisfied non-waivable requirements*.

Closure law (canonical regression: Issue #1109 / PR #1140):
    An issue is closed only by a matching source-level mechanism + tests + CI +
    ledger. A green test suite over a partial guard does not satisfy a
    non-waivable requirement. A test/fixture-only PR must say ``Refs #N``,
    never ``Closes #N``.

ADVISORY ONLY. The CLI always exits ``0`` regardless of verdict. The point of
this phase is to *measure* precision/recall against real PRs before any
promotion to a required blocking gate (see ``docs/governance/fake_closure_scanner.md``).
The pure functions below carry no I/O so they can be unit-tested offline.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path

__all__ = [
    "IssueVerdict",
    "ScanState",
    "ScanResult",
    "extract_closure_refs",
    "extract_refs_only",
    "evaluate_issue",
    "scan",
]

# GitHub's issue-closing keywords (case-insensitive), all documented spellings.
_CLOSURE_RE = re.compile(
    r"\b(close[sd]?|fix(?:e[sd])?|resolve[sd]?)\b\s*:?\s+#(\d+)",
    re.IGNORECASE,
)
# The non-closing "Refs #N" / "Ref #N" form a test/fixture-only PR must use.
_REFS_RE = re.compile(r"\brefs?\b\s*:?\s+#(\d+)", re.IGNORECASE)

# Fenced (```...```) and inline (`...`) code spans. Keywords inside code are
# discussion, not directives — GitHub itself ignores closing keywords there,
# so we strip code before matching to avoid matching a quoted "`Closes #N`".
_FENCED_CODE_RE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`[^`]*`")

# GFM task-list lines.
_UNCHECKED_RE = re.compile(r"^\s*[-*]\s*\[\s\]\s*(.+?)\s*$", re.MULTILINE)
_CHECKED_RE = re.compile(r"^\s*[-*]\s*\[[xX]\]\s*(.+?)\s*$", re.MULTILINE)

# The ONLY global promoter: an explicit non-waivable declaration governs the
# whole checklist (matches #1109's "**Non-waivable:**"). Kept deliberately
# narrow to hold the false-positive rate down — broad prose words like "must"
# do NOT promote a whole list.
_GLOBAL_NONWAIVABLE_RE = re.compile(r"non[-\s]?waivable", re.IGNORECASE)

# Per-item markers: an individual unchecked item is treated as a hard
# requirement when its own text carries one of these qualifiers.
_PER_ITEM_MARKERS: tuple[str, ...] = (
    "non-waivable",
    "nonwaivable",
    "release-blocking",
    "release blocking",
    "closure requirement",
    "source-level",
    "evidence-bearing",
    "same-sha ci",
    "required:",
    "acceptance:",
    "must ",
)


class IssueVerdict(str, Enum):
    """Per-issue requirement-satisfaction verdict."""

    CLEAN = "CLEAN"  # no unsatisfied non-waivable requirement
    FAIL = "FAIL"  # >=1 unsatisfied non-waivable requirement
    UNKNOWN = "UNKNOWN"  # body unavailable or unverifiable structure


class ScanState(str, Enum):
    """Aggregate scanner state for a PR body."""

    PASS = "PASS"
    ADVISORY_FAIL = "ADVISORY_FAIL"
    UNKNOWN = "UNKNOWN"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"


@dataclass(slots=True)
class ScanResult:
    """Structured, JSON-serialisable scanner output."""

    pr_number: int
    state: ScanState
    closure_claims: list[str] = field(default_factory=list)
    referenced_issues: list[int] = field(default_factory=list)
    unchecked_non_waivable_items: list[dict[str, str]] = field(default_factory=list)
    evidence_gap: str = ""
    recommended_action: str = ""
    blocking_recommended: bool = False  # always False in the advisory phase

    def to_json(self) -> str:
        payload = asdict(self)
        payload["state"] = self.state.value
        return json.dumps(payload, indent=2, sort_keys=True)


def _strip_code(text: str) -> str:
    """Remove fenced and inline code spans so quoted keywords are not matched."""
    without_fenced = _FENCED_CODE_RE.sub(" ", text)
    return _INLINE_CODE_RE.sub(" ", without_fenced)


def extract_closure_refs(pr_body: str) -> dict[int, str]:
    """Map issue number -> the closure phrase (e.g. ``Closes #1109``) found."""
    out: dict[int, str] = {}
    for match in _CLOSURE_RE.finditer(_strip_code(pr_body or "")):
        issue = int(match.group(2))
        # First occurrence wins for the human-readable phrase.
        out.setdefault(issue, match.group(0).strip())
    return out


def extract_refs_only(pr_body: str) -> set[int]:
    """Return issue numbers referenced via the non-closing ``Refs #N`` form."""
    return {int(m.group(1)) for m in _REFS_RE.finditer(_strip_code(pr_body or ""))}


def evaluate_issue(issue_body: str | None) -> tuple[IssueVerdict, list[str]]:
    """Classify one issue body's non-waivable requirement satisfaction.

    Returns the verdict plus the list of unsatisfied (unchecked) requirement
    texts that drove a ``FAIL``.
    """
    if issue_body is None or not issue_body.strip():
        return IssueVerdict.UNKNOWN, []

    unchecked = [m.group(1).strip() for m in _UNCHECKED_RE.finditer(issue_body)]
    checked = [m.group(1).strip() for m in _CHECKED_RE.finditer(issue_body)]
    has_global_marker = bool(_GLOBAL_NONWAIVABLE_RE.search(issue_body))

    if has_global_marker:
        # A non-waivable declaration with no parseable checklist cannot be
        # verified either way -> do not guess.
        if not unchecked and not checked:
            return IssueVerdict.UNKNOWN, []
        if unchecked:
            return IssueVerdict.FAIL, unchecked
        return IssueVerdict.CLEAN, []

    # No global declaration: only items that self-qualify as requirements count.
    flagged = [item for item in unchecked if _item_is_requirement(item)]
    if flagged:
        return IssueVerdict.FAIL, flagged
    return IssueVerdict.CLEAN, []


def _item_is_requirement(item_text: str) -> bool:
    lowered = item_text.lower()
    return any(marker in lowered for marker in _PER_ITEM_MARKERS)


def scan(pr_body: str, issue_bodies: dict[int, str | None], pr_number: int = 0) -> ScanResult:
    """Run the advisory scan over a PR body and its referenced issue bodies.

    ``issue_bodies`` maps issue number -> body text (``None`` when the body
    could not be fetched). Only issues referenced by a *closing* keyword are
    evaluated; a bare ``Refs #N`` is, by construction, out of scope.
    """
    closure_refs = extract_closure_refs(pr_body)
    if not closure_refs:
        return ScanResult(
            pr_number=pr_number,
            state=ScanState.OUT_OF_SCOPE,
            recommended_action="No closing keyword in PR body; nothing to verify.",
        )

    referenced = sorted(closure_refs)
    unsatisfied: list[dict[str, str]] = []
    any_fail = False
    any_unknown = False

    for issue in referenced:
        verdict, items = evaluate_issue(issue_bodies.get(issue))
        if verdict is IssueVerdict.FAIL:
            any_fail = True
            for item in items:
                unsatisfied.append({"issue": f"#{issue}", "item": item})
        elif verdict is IssueVerdict.UNKNOWN:
            any_unknown = True

    if any_fail:
        state = ScanState.ADVISORY_FAIL
        gap = (
            "Closing-keyword issue(s) still carry unchecked non-waivable "
            "requirements; the diff likely does not satisfy them."
        )
        action = (
            "Downgrade the affected 'Closes #N' to 'Refs #N' until the issue's "
            "non-waivable checklist is fully satisfied by a source-level mechanism."
        )
    elif any_unknown:
        state = ScanState.UNKNOWN
        gap = "One or more referenced issue bodies were unavailable or unverifiable."
        action = "Fetch issue bodies / clarify the checklist, then re-scan."
    else:
        state = ScanState.PASS
        gap = ""
        action = "Closure claims are consistent with satisfied issue requirements."

    return ScanResult(
        pr_number=pr_number,
        state=state,
        closure_claims=[closure_refs[i] for i in referenced],
        referenced_issues=referenced,
        unchecked_non_waivable_items=unsatisfied,
        evidence_gap=gap,
        recommended_action=action,
        blocking_recommended=False,
    )


# --------------------------------------------------------------------------- #
# Thin I/O layer (not exercised by the offline unit tests).
# --------------------------------------------------------------------------- #


def _gh_json(args: list[str]) -> dict[str, object]:
    proc = subprocess.run(
        ["gh", *args],
        capture_output=True,
        text=True,
        check=True,
    )
    parsed: dict[str, object] = json.loads(proc.stdout)
    return parsed


def _fetch_pr_body(pr_number: int, repo: str) -> str:
    data = _gh_json(["pr", "view", str(pr_number), "--repo", repo, "--json", "body"])
    body = data.get("body")
    return body if isinstance(body, str) else ""


def _fetch_issue_body(issue_number: int, repo: str) -> str | None:
    try:
        data = _gh_json(["issue", "view", str(issue_number), "--repo", repo, "--json", "body"])
    except (subprocess.CalledProcessError, json.JSONDecodeError):
        return None
    body = data.get("body")
    return body if isinstance(body, str) else None


def _issue_number_from_path(path: Path) -> int | None:
    match = re.search(r"(\d{2,})", path.stem)
    return int(match.group(1)) if match else None


def _run_live(pr_number: int, repo: str) -> ScanResult:
    pr_body = _fetch_pr_body(pr_number, repo)
    refs = extract_closure_refs(pr_body)
    issue_bodies: dict[int, str | None] = {issue: _fetch_issue_body(issue, repo) for issue in refs}
    return scan(pr_body, issue_bodies, pr_number=pr_number)


def _run_offline(body_file: Path, issue_files: list[Path]) -> ScanResult:
    pr_body = body_file.read_text(encoding="utf-8")
    refs = extract_closure_refs(pr_body)
    issue_bodies: dict[int, str | None] = {}
    for path in issue_files:
        number = _issue_number_from_path(path)
        if number is None and len(refs) == 1 and len(issue_files) == 1:
            number = next(iter(refs))
        if number is not None:
            issue_bodies[number] = path.read_text(encoding="utf-8")
    return scan(pr_body, issue_bodies, pr_number=0)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Advisory fake-closure scanner (never blocks).")
    parser.add_argument("--pr", type=int, help="PR number to scan via gh.")
    parser.add_argument(
        "--repo", default="neuron7xLab/GeoSync", help="owner/name for live --pr mode."
    )
    parser.add_argument("--body-file", type=Path, help="Offline: path to a PR-body markdown file.")
    parser.add_argument(
        "--issue-file",
        type=Path,
        action="append",
        default=[],
        help="Offline: issue-body markdown file (repeatable; number inferred from filename).",
    )
    args = parser.parse_args(argv)

    if args.pr is not None:
        result = _run_live(args.pr, args.repo)
    elif args.body_file is not None:
        result = _run_offline(args.body_file, list(args.issue_file))
    else:
        parser.error("provide --pr N or --body-file FILE [--issue-file FILE ...]")

    print(result.to_json())
    # ADVISORY: never block. Verdict lives in the JSON 'state' field.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
