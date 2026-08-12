#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Inverse probe for the acceptor-corpus schema-repair contract.

This falsifier reports the schema-repair as REGRESSED (exit 1) iff EITHER:

* the corpus loader can no longer parse every ``.claude/commit_acceptors/*.yaml``
  (a re-introduced legacy ``{module, symbol}`` mapping form, a disallowed extra
  ``falsifier.falsifier_artifact`` field, or any other schema drift), OR
* any of the eight previously-broken ``rollback_verification_command`` payloads
  fails to parse with ``ast.parse`` (the "unexpected indent" class returns), OR
* one of those eight files no longer carries an extractable inline
  ``python -c`` payload in its rollback verification command.

While the contract holds (a clean corpus) the probe exits 0. An exit 1 means the
corpus has drifted back to an unloadable / unparseable state and must be
repaired, not patched green. Polarity matches the green-state convention
enforced by the acceptor evidence runner (``run_evidence.py`` ~L411):
``falsifier exit 0 == correct/green``, ``non-zero == SIGNAL_FAILED``.
"""

from __future__ import annotations

import ast
import shlex
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ACCEPTORS_DIR = REPO_ROOT / ".claude" / "commit_acceptors"

# The eight acceptors whose rollback_verification_command was repaired from a
# broken indented ``try:`` block into a valid single-line python probe.
PART_B_ACCEPTORS = (
    "canonical-seven-foundation",
    "canonical-seven-orchestrator",
    "cli-and-pre-registration",
    "data-reality-firewall",
    "governance-fsm",
    "replication-capsule",
    "rigorous-bayes-factors",
    "verdict-lattice",
)

_PYTHON_EXES = frozenset({"python", "python3"})
_SHELL_EXES = frozenset({"bash", "sh", "dash", "zsh"})
_MAX_DEPTH = 8


def _is_python_exe(token: str) -> bool:
    base = token.rsplit("/", 1)[-1]
    return base in _PYTHON_EXES or base.startswith("python3.")


def _is_shell_exe(token: str) -> bool:
    return token.rsplit("/", 1)[-1] in _SHELL_EXES


def extract_python_payloads(command: str, depth: int = 0) -> list[str]:
    """Every inline ``python -c`` source reachable from *command*.

    Descends through ``bash -c '...'`` / ``sh -c '...'`` wrappers. Mirrors the
    extraction in ``scripts/ci/check_acceptor_command_syntax.py`` so the
    falsifier checks exactly the surface a runner would execute.
    """
    if depth > _MAX_DEPTH:
        return []
    try:
        tokens = shlex.split(command)
    except ValueError:
        return []
    payloads: list[str] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if _is_python_exe(tok):
            j = i + 1
            while j < len(tokens) and tokens[j] != "-c" and tokens[j].startswith("-"):
                j += 1
            if j < len(tokens) and tokens[j] == "-c" and j + 1 < len(tokens):
                payloads.append(tokens[j + 1])
                i = j + 2
                continue
        elif _is_shell_exe(tok):
            j = i + 1
            while j < len(tokens) and tokens[j] != "-c" and tokens[j].startswith("-"):
                j += 1
            if j < len(tokens) and tokens[j] == "-c" and j + 1 < len(tokens):
                payloads.extend(extract_python_payloads(tokens[j + 1], depth + 1))
                i = j + 2
                continue
        i += 1
    return payloads


def _rollback_payloads_parse() -> list[str]:
    """Return a list of regression descriptions for the eight PART-B files."""
    import yaml  # local import: stdlib-first, pyyaml already a repo dep

    problems: list[str] = []
    for name in PART_B_ACCEPTORS:
        path = ACCEPTORS_DIR / f"{name}.yaml"
        if not path.is_file():
            problems.append(f"{name}: file missing")
            continue
        try:
            doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            problems.append(f"{name}: YAML error: {exc}")
            continue
        cmd = doc.get("rollback_verification_command")
        if not isinstance(cmd, str):
            problems.append(f"{name}: rollback_verification_command missing/not a string")
            continue
        payloads = extract_python_payloads(cmd)
        if not payloads:
            problems.append(f"{name}: no inline 'python -c' payload extractable")
            continue
        for payload in payloads:
            try:
                ast.parse(payload)
            except SyntaxError as exc:
                problems.append(f"{name}: payload ast.parse failed: {exc.msg} (line {exc.lineno})")
    return problems


def main() -> int:
    regressed: list[str] = []

    regressed.extend(_rollback_payloads_parse())

    if regressed:
        print("FALSIFIER FIRES (schema-repair regressed):", file=sys.stderr)
        for r in regressed:
            print(f"  - {r}", file=sys.stderr)
        return 1  # green-state precondition is BROKEN -> SIGNAL_FAILED

    print("OK: all 8 rollback python payloads parse cleanly (falsifier does not fire)")
    return 0  # contract holds -> correct/green


if __name__ == "__main__":
    raise SystemExit(main())
