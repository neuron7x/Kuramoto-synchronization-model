#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Fail-closed gate for the remediation ledger (task DS-11 / GOV-003).

``governance/remediation_ledger.v1.json`` is the single machine-readable
risk/debt register (SSOT). Before this gate it had **no** validating CI hook:
its schema was never executed and the committed ledger was already
schema-invalid (a status value outside the enum). A register nobody validates
is a register nobody can trust — ``closed ⟹ PASS`` was an unenforced promise.

This gate proves the ledger is honest. It fails closed (RED) when:

  1. the ledger does not validate against
     ``governance/remediation_ledger.v1.schema.json``;
  2. any item with ``status == "closed"`` lacks
     ``reviewer_signoff.verdict == "PASS"`` (closed-without-PASS is the core
     fail-open a governance ledger must never permit);
  3. any *literal* path cited in a **closed** item's ``source_evidence`` does
     not exist on disk (dangling evidence). Scope is closed items only: a
     closed item asserts its evidence is produced, whereas an open/in_progress
     item's ``source_evidence`` names *planned* artifacts that legitimately do
     not exist yet. ``source_evidence`` is free-form prose, so only tokens
     rooted at a real repository directory are treated as paths;
     glob/enumeration shorthand (``*``, ``{a,b}``) is verified at the
     directory level, never suppressed;
  4. ``baseline_tree`` does not resolve to a real git object
     (``git cat-file -e``) — a baseline that no longer exists is not a baseline.

Exit codes::

    0  — ledger valid, every closed item signed PASS, evidence present,
         baseline resolves
    1  — at least one violation (RED)
    2  — misconfiguration: missing ledger/schema, or a missing dependency
         (jsonschema) — never a raw traceback

The gate is deliberately independent of the heavy repo-level conftest and imports
only the stdlib plus ``jsonschema`` (guarded).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

try:
    import jsonschema
except ImportError as exc:  # pragma: no cover - exercised via subprocess in CI
    print(
        f"check_remediation_ledger: missing dependency: {exc}. "
        f"Install jsonschema to run this gate.",
        file=sys.stderr,
    )
    raise SystemExit(2)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LEDGER = ROOT / "governance" / "remediation_ledger.v1.json"
DEFAULT_SCHEMA = ROOT / "governance" / "remediation_ledger.v1.schema.json"

# Characters that make a source_evidence token a glob/enumeration rather than a
# single literal path.
_GLOB_META = set("*?{}[]")
# Split source_evidence prose into whitespace/semicolon/comma-delimited tokens.
_TOKEN_RE = re.compile(r"[^\s;,]+")


def _path_candidates(source_evidence: str, root: Path) -> list[str]:
    """Extract path-like tokens from a free-form ``source_evidence`` string.

    A token counts as a path candidate only if its first ``/``-segment is an
    existing directory under ``root``. This anchors extraction to the real
    repository tree and rejects prose (``test(6)``, ``1.1.0``), bare filenames,
    and slash-joined enumerations rooted at non-directories.
    """
    out: list[str] = []
    for raw in _TOKEN_RE.findall(source_evidence):
        # Strip a trailing "(...)" annotation and stray punctuation.
        tok = re.sub(r"\(.*$", "", raw).strip().rstrip(".;,")
        if "/" not in tok:
            continue
        first = tok.split("/", 1)[0]
        if (root / first).is_dir():
            out.append(tok)
    return out


def _evidence_problem(tok: str, root: Path) -> str | None:
    """Return a failure string if a source_evidence path token is dangling."""
    meta_pos = next((i for i, ch in enumerate(tok) if ch in _GLOB_META), None)
    if meta_pos is None:
        # Literal path: it must exist exactly.
        return None if (root / tok).exists() else f"missing evidence path {tok!r}"
    # Glob / enumeration shorthand: verify the cited directory exists and is
    # non-empty (lenient but not suppressed — a fabricated directory still RED).
    prefix = tok[:meta_pos]
    directory = (root / prefix).parent if not prefix.endswith("/") else root / prefix
    if not directory.is_dir():
        return f"evidence glob {tok!r} — directory {directory} does not exist"
    if not any(directory.iterdir()):
        return f"evidence glob {tok!r} — directory {directory} is empty"
    return None


def _baseline_resolves(tree: str, git_root: Path) -> bool:
    if not tree:
        return False
    try:
        proc = subprocess.run(
            ["git", "cat-file", "-e", f"{tree}^{{}}"],
            cwd=str(git_root),
            capture_output=True,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0


def check_ledger(
    ledger: dict,
    schema: dict,
    root: Path,
    git_root: Path,
) -> list[str]:
    """Return a list of failure strings for one ledger (empty == OK)."""
    problems: list[str] = []

    # 1. schema validity.
    validator = jsonschema.Draft202012Validator(schema)
    for err in sorted(validator.iter_errors(ledger), key=lambda e: list(e.path)):
        loc = "/".join(str(p) for p in err.path) or "<root>"
        problems.append(f"schema: {loc}: {err.message}")
    if problems:
        # A schema-invalid ledger may lack fields the checks below rely on.
        return problems

    items = ledger.get("items") or []
    for item in items:
        iid = item.get("id", "<no-id>")
        status = item.get("status")

        # 2. closed ⟹ reviewer_signoff.verdict == PASS (fail-closed).
        if status == "closed":
            verdict = (item.get("reviewer_signoff") or {}).get("verdict")
            if verdict != "PASS":
                problems.append(
                    f"{iid}: status=closed but reviewer_signoff.verdict="
                    f"{verdict!r} (closed without an independent PASS sign-off)"
                )

        # 3. source_evidence literal paths must exist on disk — but only for
        # CLOSED items. A closed item asserts the work AND its evidence are
        # done; an open/in_progress item's source_evidence names the *planned*
        # artifacts that do not exist yet. Requiring existence on non-closed
        # items would be a category error, not a fail-closed control.
        if status == "closed":
            for tok in _path_candidates(str(item.get("source_evidence", "")), root):
                prob = _evidence_problem(tok, root)
                if prob:
                    problems.append(f"{iid}: {prob}")

    # 4. baseline_tree must resolve to a real git object.
    baseline = str(ledger.get("baseline_tree", ""))
    if baseline and not _baseline_resolves(baseline, git_root):
        problems.append(
            f"baseline_tree {baseline!r} does not resolve to a git object "
            f"(git cat-file -e failed in {git_root})"
        )

    return problems


def run(ledger_path: Path, schema_path: Path, root: Path, git_root: Path) -> int:
    if not ledger_path.exists():
        print(f"ledger not found: {ledger_path}", file=sys.stderr)
        return 2
    if not schema_path.exists():
        print(f"schema not found: {schema_path}", file=sys.stderr)
        return 2

    try:
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"{ledger_path.name}: invalid JSON ({exc})", file=sys.stderr)
        return 1
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)

    problems = check_ledger(ledger, schema, root, git_root)

    if problems:
        print(
            f"\nRemediation ledger gate FAILED (RED): {len(problems)} problem(s).",
            file=sys.stderr,
        )
        for line in problems:
            print(f"  - {line}", file=sys.stderr)
        return 1

    items = ledger.get("items") or []
    closed = sum(1 for i in items if i.get("status") == "closed")
    print(
        f"\nRemediation ledger gate PASSED: {len(items)} item(s), {closed} closed "
        f"(all PASS-signed), evidence paths present, baseline_tree resolves."
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate the remediation ledger (DS-11 / GOV-003)."
    )
    parser.add_argument(
        "--ledger", type=Path, default=DEFAULT_LEDGER, help="Path to remediation_ledger.v1.json."
    )
    parser.add_argument(
        "--schema",
        type=Path,
        default=DEFAULT_SCHEMA,
        help="Path to remediation_ledger.v1.schema.json.",
    )
    parser.add_argument(
        "--root", type=Path, default=ROOT, help="Repo root used to resolve source_evidence paths."
    )
    parser.add_argument(
        "--git-root",
        type=Path,
        default=ROOT,
        help="Git working tree used to resolve baseline_tree.",
    )
    args = parser.parse_args(argv)
    return run(
        args.ledger.resolve(),
        args.schema.resolve(),
        args.root.resolve(),
        args.git_root.resolve(),
    )


if __name__ == "__main__":
    raise SystemExit(main())
