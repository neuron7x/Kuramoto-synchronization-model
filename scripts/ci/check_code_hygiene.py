#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Code-hygiene ratchet — fail-closed, monotone-down debt ledger.

Sibling of ``check_import_architecture.py``: the import ratchet pins the
*package-boundary* debt, this one pins the *intra-module* debt that erodes
local reasoning, fail-closed runtime behaviour and deterministic tests.

It scans the first-party ``runtime_roots`` declared in
``docs/CODE_QUALITY_MANIFEST.json`` and freezes today's reality in
``docs/CODE_DEBT_BASELINE.json`` across six dimensions:

* ``god_function``         — function/method LOC over ``max_function_loc``
* ``god_class``            — class LOC over ``max_class_loc``
* ``complexity``           — function cyclomatic complexity over ``max_complexity``
* ``god_file``             — file physical LOC over ``max_file_loc``
* ``broad_except``         — bare / ``Exception`` / ``BaseException`` handlers
* ``runtime_print``        — ``print(...)`` calls (not observability)
* ``ambient_nondeterminism`` — ambient clock / RNG / sleep calls

The first four are tracked as a *symbol set* (key ``path::qualname``); a NEW
symbol over budget fails the build, a baseline symbol that no longer violates
must be retired (``--write``). The last three are tracked as a *per-file
count*; any file whose count rises — or any new violating file — fails, any
file whose count drops must be tightened. Both styles only ever shrink, so
the ledger trends to empty and can never silently accrue fresh debt.

This is a gate, not a refactor: it changes no runtime behaviour. The TARGET
is every list empty; the path there is paying down the baseline. See
``docs/adr/0025-code-hygiene-ratchet.md`` and ``docs/DETERMINISM_POLICY.md``.

Usage::

    python scripts/ci/check_code_hygiene.py            # verify (CI)
    python scripts/ci/check_code_hygiene.py --write     # tighten the ledger

Exit codes::

    0  — current debt <= baseline, no stale entry
    1  — new violator entered, or a paid-down entry must be retired
"""

from __future__ import annotations

import argparse
import ast
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = ROOT / "docs" / "CODE_QUALITY_MANIFEST.json"
BASELINE_PATH = ROOT / "docs" / "CODE_DEBT_BASELINE.json"

# ``unparseable`` is the fail-closed guard (V4): a runtime file that won't
# AST-parse — e.g. newer syntax under an older runner — must surface as
# visible debt, never silently contribute zero. SYMBOL_DIMS are keyed by
# ``path::qualname`` (``path`` alone for god_file/unparseable).
SYMBOL_DIMS = ("god_function", "god_class", "complexity", "god_file", "unparseable")
COUNT_DIMS = ("broad_except", "runtime_print", "ambient_nondeterminism")

# Ambient nondeterminism, matched on the trailing dotted components of a call
# target so aliasing of the package root does not hide it
# (``np.random.seed`` -> ``random.seed``; ``datetime.datetime.now`` -> ``datetime.now``).
_AMBIENT_SUFFIX_2 = frozenset(
    {
        "datetime.now",
        "datetime.utcnow",
        "datetime.today",
        "time.time",
        "time.time_ns",
        "time.monotonic",
        "time.perf_counter",
        "time.sleep",
        "asyncio.sleep",
        "random.random",
        "random.seed",
        "random.randint",
        "random.uniform",
        "random.choice",
        "random.default_rng",
        "random.rand",
        "random.randn",
    }
)
# Unambiguous single names that need no qualifier to be obviously ambient.
_AMBIENT_NAME_1 = frozenset({"default_rng", "perf_counter", "monotonic", "time_ns"})
_BROAD_NAMES = frozenset({"Exception", "BaseException"})


def _load_manifest() -> tuple[list[str], list[str], dict[str, int]]:
    payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return (
        list(payload["runtime_roots"]),
        list(payload.get("excluded_roots", [])),
        dict(payload["thresholds"]),
    )


def _is_test_path(rel: str) -> bool:
    """pytest-convention test file nested anywhere under a runtime root.

    The manifest's ``excluded_roots`` only catches top-level ``tests/``; test
    files living *inside* a runtime package (``core/neuro/tests/...``,
    ``geosync/dp3_test.py``) were being miscounted as runtime debt — tests
    legitimately use ``random``/``time`` and broad excepts. Match the same
    surface pytest collects: a ``/tests/`` or ``/test/`` segment, or a
    ``test_*.py`` / ``*_test.py`` / ``conftest.py`` basename.
    """
    if "/tests/" in rel or "/test/" in rel:
        return True
    name = rel.rsplit("/", 1)[-1]
    return name == "conftest.py" or name.startswith("test_") or name.endswith("_test.py")


def _iter_py(roots: list[str], excluded: tuple[str, ...]) -> list[Path]:
    out: list[Path] = []
    for root in roots:
        base = ROOT / root
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            rel = path.relative_to(ROOT).as_posix()
            if any(rel == e or rel.startswith(e + "/") for e in excluded):
                continue
            if _is_test_path(rel):
                continue
            out.append(path)
    return sorted(out)


def _dotted(func: ast.expr) -> str | None:
    """Reconstruct a dotted call target (``a.b.c``) or return None."""
    parts: list[str] = []
    node: ast.expr | None = func
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    elif node is not None:
        return None  # call/subscript/literal base — not a stable dotted name
    return ".".join(reversed(parts)) if parts else None


def _alias_map(tree: ast.AST) -> dict[str, str]:
    """Map a file's local import names to their canonical dotted target, so an
    aliased ambient call survives detection (V7): ``import datetime as DT`` makes
    ``DT.now()`` resolve to ``datetime.now``; ``from time import time as t`` makes
    ``t()`` resolve to ``time.time``."""
    out: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                local = a.asname or a.name.split(".")[0]
                out[local] = a.name if a.asname else a.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            for a in node.names:
                out[a.asname or a.name] = f"{node.module}.{a.name}"
    return out


def _complexity(node: ast.AST) -> int:
    """McCabe cyclomatic complexity: 1 + count of decision points."""
    score = 1
    for child in ast.walk(node):
        if isinstance(
            child,
            (
                ast.If,
                ast.IfExp,
                ast.For,
                ast.AsyncFor,
                ast.While,
                ast.ExceptHandler,
                ast.Assert,
                ast.With,
                ast.AsyncWith,
            ),
        ):
            score += 1
        elif isinstance(child, ast.BoolOp):
            score += len(child.values) - 1
        elif isinstance(child, ast.comprehension):
            score += 1 + len(child.ifs)
        elif isinstance(child, ast.match_case):
            score += 1
    return score


def _is_broad(handler: ast.ExceptHandler) -> bool:
    exc = handler.type
    if exc is None:
        return True
    names = exc.elts if isinstance(exc, ast.Tuple) else [exc]
    return any(isinstance(n, ast.Name) and n.id in _BROAD_NAMES for n in names)


def _scan_file(
    rel: str, source: str, thr: dict[str, int]
) -> tuple[dict[str, set[str]], dict[str, int]]:
    """Return this file's contribution to every debt dimension."""
    syms: dict[str, set[str]] = {d: set() for d in SYMBOL_DIMS}
    counts: dict[str, int] = {d: 0 for d in COUNT_DIMS}
    try:
        tree = ast.parse(source, filename=rel)
    except SyntaxError:
        syms["unparseable"].add(rel)  # V4: fail-closed, never silent zero
        return syms, counts

    file_loc = len(source.splitlines())
    if file_loc > thr["max_file_loc"]:
        syms["god_file"].add(rel)

    aliases = _alias_map(tree)

    def walk(node: ast.AST, prefix: str) -> None:
        for child in ast.iter_child_nodes(node):
            qual = prefix
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qual = f"{prefix}.{child.name}" if prefix else child.name
                loc = (child.end_lineno or child.lineno) - child.lineno + 1
                key = f"{rel}::{qual}"
                if loc > thr["max_function_loc"]:
                    syms["god_function"].add(key)
                if _complexity(child) > thr["max_complexity"]:
                    syms["complexity"].add(key)
            elif isinstance(child, ast.ClassDef):
                qual = f"{prefix}.{child.name}" if prefix else child.name
                loc = (child.end_lineno or child.lineno) - child.lineno + 1
                if loc > thr["max_class_loc"]:
                    syms["god_class"].add(f"{rel}::{qual}")
            elif isinstance(child, ast.ExceptHandler) and _is_broad(child):
                counts["broad_except"] += 1
            elif isinstance(child, ast.Call):
                target = _dotted(child.func)
                if isinstance(child.func, ast.Name) and child.func.id == "print":
                    counts["runtime_print"] += 1
                elif target is not None:
                    bits = target.split(".")
                    canonical = aliases.get(bits[0])
                    if canonical:  # V7: rewrite an aliased base to its canonical
                        bits = canonical.split(".") + bits[1:]
                    suffix2 = ".".join(bits[-2:])
                    if suffix2 in _AMBIENT_SUFFIX_2 or bits[-1] in _AMBIENT_NAME_1:
                        counts["ambient_nondeterminism"] += 1
            walk(child, qual)

    walk(tree, "")
    return syms, counts


def _classification_gaps() -> list[str]:
    """V5: top-level packages with .py that are in neither runtime nor excluded.

    Forces every new top-level package to be deliberately classified, so the
    gated surface cannot silently shrink as the repo grows. Dot-prefixed
    directories (``.github``, ``.claude``) are tooling, not packages.
    """
    roots, excluded, _ = _load_manifest()
    classified = set(roots) | {e.split("/", 1)[0] for e in excluded}
    proc = subprocess.run(
        ["git", "ls-files", "*.py"], cwd=ROOT, capture_output=True, text=True, check=False
    )
    top: set[str] = set()
    for line in proc.stdout.splitlines():
        if "/" in line and not line.startswith("."):
            top.add(line.split("/", 1)[0])
    return sorted(top - classified)


def _scan() -> tuple[dict[str, set[str]], dict[str, dict[str, int]]]:
    roots, excluded, thr = _load_manifest()
    syms: dict[str, set[str]] = {d: set() for d in SYMBOL_DIMS}
    counts: dict[str, dict[str, int]] = {d: {} for d in COUNT_DIMS}
    for path in _iter_py(roots, tuple(excluded)):
        rel = path.relative_to(ROOT).as_posix()
        source = path.read_text(encoding="utf-8", errors="replace")
        syms_part, counts_part = _scan_file(rel, source, thr)
        for dim in SYMBOL_DIMS:
            syms[dim] |= syms_part[dim]
        for dim in COUNT_DIMS:
            n = counts_part[dim]
            if n:
                counts[dim][rel] = n
    return syms, counts


def _load_baseline() -> tuple[dict[str, set[str]], dict[str, dict[str, int]]]:
    syms: dict[str, set[str]] = {d: set() for d in SYMBOL_DIMS}
    counts: dict[str, dict[str, int]] = {d: {} for d in COUNT_DIMS}
    if not BASELINE_PATH.exists():
        return syms, counts
    payload = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    for dim in SYMBOL_DIMS:
        syms[dim] = set(payload.get("symbol_debt", {}).get(dim, []))
    for dim in COUNT_DIMS:
        counts[dim] = dict(payload.get("file_count_debt", {}).get(dim, {}))
    return syms, counts


def _write_baseline(syms: dict[str, set[str]], counts: dict[str, dict[str, int]]) -> None:
    _, _, thr = _load_manifest()
    payload = {
        "_doc": (
            "Code-hygiene debt ledger (RATCHET). Frozen reality of intra-module "
            "debt across the runtime_roots in docs/CODE_QUALITY_MANIFEST.json. "
            "symbol_debt sets and file_count_debt maps may ONLY shrink; "
            "scripts/ci/check_code_hygiene.py fails on any new violator and on "
            "any paid-down entry left stale. Target: every list/map empty. "
            "See docs/adr/0025-code-hygiene-ratchet.md."
        ),
        "schema_version": "1.0",
        "thresholds_snapshot": thr,
        "symbol_debt": {d: sorted(syms[d]) for d in SYMBOL_DIMS},
        "file_count_debt": {d: {k: counts[d][k] for k in sorted(counts[d])} for d in COUNT_DIMS},
    }
    BASELINE_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Code-hygiene ratchet.")
    parser.add_argument(
        "--write",
        action="store_true",
        help="Regenerate the baseline from the current tree (tighten the ledger).",
    )
    args = parser.parse_args(argv)

    cur_syms, cur_counts = _scan()

    if args.write:
        _write_baseline(cur_syms, cur_counts)
        tot_s = sum(len(cur_syms[d]) for d in SYMBOL_DIMS)
        tot_c = sum(sum(cur_counts[d].values()) for d in COUNT_DIMS)
        print(f"Baseline tightened: {tot_s} over-budget symbols, {tot_c} flagged call-sites.")
        return 0

    base_syms, base_counts = _load_baseline()
    failed = False

    gaps = _classification_gaps()
    if gaps:
        failed = True
        print(
            "ERROR: unclassified top-level package(s) with .py — the gated surface "
            "may not silently shrink. Add each to runtime_roots (gated) or "
            "excluded_roots (deliberately ungated) in docs/CODE_QUALITY_MANIFEST.json:"
        )
        for g in gaps:
            print(f"  ? {g}")

    for dim in SYMBOL_DIMS:
        new = sorted(cur_syms[dim] - base_syms[dim])
        fixed = sorted(base_syms[dim] - cur_syms[dim])
        if new:
            failed = True
            print(f"ERROR: new {dim} debt (the code-hygiene ratchet only shrinks):")
            for k in new:
                print(f"  + {k}")
        if fixed:
            failed = True
            print(f"{dim}: {len(fixed)} entr(y/ies) paid down but ledger stale — tighten it.")

    for dim in COUNT_DIMS:
        rose = sorted(f for f, n in cur_counts[dim].items() if n > base_counts[dim].get(f, 0))
        dropped = sorted(f for f, n in base_counts[dim].items() if cur_counts[dim].get(f, 0) < n)
        if rose:
            failed = True
            print(f"ERROR: {dim} count rose (or new file) — only shrinks:")
            for f in rose:
                print(f"  + {f}: {base_counts[dim].get(f, 0)} -> {cur_counts[dim][f]}")
        if dropped:
            failed = True
            print(f"{dim}: {len(dropped)} file(s) improved but ledger stale — tighten it.")

    if failed:
        print("Fix: keep code under budget, or run --write only when paying debt DOWN.")
        print("  python scripts/ci/check_code_hygiene.py --write")
        return 1

    tot_s = sum(len(cur_syms[d]) for d in SYMBOL_DIMS)
    tot_c = sum(sum(cur_counts[d].values()) for d in COUNT_DIMS)
    print(
        f"Code-hygiene ratchet held: {tot_s} over-budget symbols + "
        f"{tot_c} flagged call-sites (target 0). No new debt."
    )
    if tot_s == 0 and tot_c == 0:
        print("Ledger empty — runtime roots within complexity/exception/determinism budget.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
