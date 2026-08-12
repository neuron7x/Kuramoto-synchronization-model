#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Mutation probe — falsify the verifier, not just the code.

A passing test suite proves nothing if the tests pass *vacuously*. This probe
adversarially mutates a module's source one site at a time (flip a comparison,
swap and/or, perturb a constant, swap +/-), runs a target test selector against
each mutant, and records whether the mutation was KILLED (a test failed — the
suite caught the behaviour change) or SURVIVED (every test still passed — a
blind spot in the suite).

The surviving mutations are the deliverable: each is a behaviour change the
test suite cannot distinguish from correct code. A high kill-rate is evidence
the suite actually verifies; survivors name exactly what it does not.

Mutations are applied by transforming the AST and re-emitting via ``ast.unparse``
(formatting differs, behaviour does not), written in place, tested, then the
original bytes are always restored in a ``finally``. Single-threaded; never
leaves the tree mutated.

Usage::

    python tools/mutation_probe.py <module.py> --tests <pytest-selector> [--max N] [--json out.json]

Exit codes::

    0  — ran to completion (see report / --fail-under for gating)
    2  — bad arguments or the baseline test selector does not pass clean
"""

from __future__ import annotations

import argparse
import ast
import copy
import json
import signal
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Semantic operator swaps. Each maps an AST op type to its mutated counterpart.
_CMP_SWAP: dict[type, type] = {
    ast.Lt: ast.GtE,
    ast.Gt: ast.LtE,
    ast.LtE: ast.Gt,
    ast.GtE: ast.Lt,
    ast.Eq: ast.NotEq,
    ast.NotEq: ast.Eq,
}
_BOOL_SWAP: dict[type, type] = {ast.And: ast.Or, ast.Or: ast.And}
_BIN_SWAP: dict[type, type] = {ast.Add: ast.Sub, ast.Sub: ast.Add, ast.Mult: ast.Div}


@dataclass
class Mutant:
    index: int
    lineno: int
    kind: str
    detail: str
    killed: bool | None = None


@dataclass
class Report:
    module: str
    tests: str
    mutants: list[Mutant] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.mutants)

    @property
    def killed(self) -> int:
        return sum(1 for m in self.mutants if m.killed)

    @property
    def survived(self) -> list[Mutant]:
        return [m for m in self.mutants if m.killed is False]

    @property
    def kill_rate(self) -> float:
        return (self.killed / self.total) if self.total else 1.0


def _sites(tree: ast.AST) -> list[tuple[str, str]]:
    """Enumerate mutable sites in source order; returns (kind, detail) per site."""
    out: list[tuple[str, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            for op in node.ops:
                if type(op) in _CMP_SWAP:
                    out.append(("compare", type(op).__name__))
        elif isinstance(node, ast.BoolOp) and type(node.op) in _BOOL_SWAP:
            out.append(("boolop", type(node.op).__name__))
        elif isinstance(node, ast.BinOp) and type(node.op) in _BIN_SWAP:
            out.append(("binop", type(node.op).__name__))
        elif isinstance(node, ast.Constant):
            if isinstance(node.value, bool):
                out.append(("bool_const", repr(node.value)))
            elif isinstance(node.value, int) and not isinstance(node.value, bool):
                out.append(("int_const", repr(node.value)))
    return out


def _apply(tree: ast.AST, target: int) -> tuple[ast.AST, int, str, str]:
    """Apply exactly the mutation at site `target`; return (tree, lineno, kind, detail)."""
    counter = [0]
    info: dict[str, object] = {}

    def mutate_op(node: ast.AST, op: ast.AST, swap: dict[type, type], kind: str) -> ast.AST:
        if type(op) in swap:
            if counter[0] == target:
                info["lineno"] = getattr(node, "lineno", -1)
                info["kind"] = kind
                info["detail"] = f"{type(op).__name__}->{swap[type(op)].__name__}"
                counter[0] += 1
                return swap[type(op)]()
            counter[0] += 1
        return op

    class T(ast.NodeTransformer):
        def visit_Compare(self, node: ast.Compare) -> ast.AST:
            self.generic_visit(node)
            node.ops = [mutate_op(node, op, _CMP_SWAP, "compare") for op in node.ops]
            return node

        def visit_BoolOp(self, node: ast.BoolOp) -> ast.AST:
            self.generic_visit(node)
            node.op = mutate_op(node, node.op, _BOOL_SWAP, "boolop")
            return node

        def visit_BinOp(self, node: ast.BinOp) -> ast.AST:
            self.generic_visit(node)
            node.op = mutate_op(node, node.op, _BIN_SWAP, "binop")
            return node

        def visit_Constant(self, node: ast.Constant) -> ast.AST:
            if isinstance(node.value, bool):
                if counter[0] == target:
                    info["lineno"], info["kind"] = node.lineno, "boolconst"
                    info["detail"] = f"{node.value}->{not node.value}"
                    counter[0] += 1
                    return ast.copy_location(ast.Constant(value=not node.value), node)
                counter[0] += 1
            elif isinstance(node.value, int) and not isinstance(node.value, bool):
                if counter[0] == target:
                    info["lineno"], info["kind"] = node.lineno, "intconst"
                    info["detail"] = f"{node.value}->{node.value + 1}"
                    counter[0] += 1
                    return ast.copy_location(ast.Constant(value=node.value + 1), node)
                counter[0] += 1
            return node

    new = T().visit(copy.deepcopy(tree))
    ast.fix_missing_locations(new)
    return (
        new,
        int(info.get("lineno", -1)),
        str(info.get("kind", "?")),
        str(info.get("detail", "?")),
    )


def _run_tests(selector: str) -> bool:
    """Return True iff the selector passes (exit 0)."""
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-x", "-q", "-p", "no:cacheprovider", *selector.split()],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    return proc.returncode == 0


def probe(
    module: str, tests: str, max_mutants: int | None, kinds: frozenset[str] | None = None
) -> Report:
    path = ROOT / module
    original = path.read_text(encoding="utf-8")
    tree = ast.parse(original)
    sites = _sites(tree)
    report = Report(module=module, tests=tests)
    indices = list(range(len(sites)))
    if max_mutants is not None:
        indices = indices[:max_mutants]

    # A plain try/finally does NOT restore the file if the process is signalled
    # (SIGTERM from a timeout, SIGINT from Ctrl-C) mid-mutation — which would
    # leave the source corrupted. A verification tool must never damage the
    # tree it probes, so restore on signal too, then re-raise the default.
    def _restore_and_exit(signum: int, _frame: object) -> None:
        path.write_text(original, encoding="utf-8")
        raise SystemExit(128 + signum)

    prev_term = signal.signal(signal.SIGTERM, _restore_and_exit)
    prev_int = signal.signal(signal.SIGINT, _restore_and_exit)
    try:
        for i in indices:
            mutant_tree, lineno, kind, detail = _apply(tree, i)
            if kinds is not None and kind not in kinds:
                continue  # skip the (expensive) test run for filtered-out kinds
            path.write_text(ast.unparse(mutant_tree) + "\n", encoding="utf-8")
            killed = not _run_tests(tests)  # a failing suite KILLS the mutant
            report.mutants.append(
                Mutant(index=i, lineno=lineno, kind=kind, detail=detail, killed=killed)
            )
    finally:
        path.write_text(original, encoding="utf-8")  # ALWAYS restore
        signal.signal(signal.SIGTERM, prev_term)
        signal.signal(signal.SIGINT, prev_int)
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Mutation probe.")
    ap.add_argument("module")
    ap.add_argument("--tests", required=True, help="pytest selector run against each mutant")
    ap.add_argument("--max", type=int, default=None, help="cap number of mutants")
    ap.add_argument("--fail-under", type=float, default=None, help="exit 1 if kill-rate below this")
    ap.add_argument(
        "--only-logic",
        action="store_true",
        help="probe ONLY compare/boolop sites (the behaviour-logic gaps), skipping "
        "constant/arithmetic mutations — much faster on numeric-heavy physics modules "
        "where tuning constants dominate and are mostly equivalent.",
    )
    ap.add_argument("--json", dest="json_out", default=None)
    args = ap.parse_args(argv)

    if not _run_tests(args.tests):
        print("ERROR: baseline test selector does not pass on unmutated code.", file=sys.stderr)
        return 2

    kinds = frozenset({"compare", "boolop"}) if args.only_logic else None
    report = probe(args.module, args.tests, args.max, kinds)
    print(f"\nMutation probe: {report.module}  (tests: {report.tests})")
    print(
        f"  mutants: {report.total} | killed: {report.killed} | kill-rate: {report.kill_rate:.1%}"
    )
    if report.survived:
        print(f"  SURVIVED ({len(report.survived)}) — behaviour changes the suite cannot detect:")
        for m in report.survived:
            print(f"    {report.module}:{m.lineno}  [{m.kind}] {m.detail}")
    else:
        print("  no survivors — every mutation was caught.")

    if args.json_out:
        payload = {
            "module": report.module,
            "tests": report.tests,
            "total": report.total,
            "killed": report.killed,
            "kill_rate": report.kill_rate,
            "survivors": [
                {"lineno": m.lineno, "kind": m.kind, "detail": m.detail} for m in report.survived
            ],
        }
        Path(args.json_out).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    if args.fail_under is not None and report.kill_rate < args.fail_under:
        print(
            f"  kill-rate {report.kill_rate:.1%} < --fail-under {args.fail_under:.1%}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
