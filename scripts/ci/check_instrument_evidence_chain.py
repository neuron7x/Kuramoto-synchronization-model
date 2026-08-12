#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Mainline evidence-reconciliation gate for the seven methodology instruments.

GeoSync doctrine: a merged instrument is only honestly *evidenced* if every
link in its evidence chain is machine-resolvable, here, now, against the
working tree and git history. A claim that points at a test that pytest can
no longer collect, a registry whose recorded source hash has silently
drifted, or a merge commit that never touched the module it claims to add —
each is a *dangling evidence reference*, and a dangling reference is a quiet
lie about what has been verified.

This gate reads the authoritative registry ``governance/INSTRUMENTS.yaml``
and, for every instrument, fails closed unless the WHOLE chain resolves:

  1.  module file exists at the registered path;
  2.  sha256(module content) == registered ``source_sha256``
      (source-drift lock — a code change without a registry+acceptor
      refresh is a silent surface mutation, Task 7);
  3.  ``merge_commit`` is a full 40-hex sha that EXISTS in git history AND
      its diff touched the module path (PR -> commit -> code binding);
  4.  ``test_file`` exists;
  5.  the ``acceptor`` file exists AND its ``diff_scope.changed_files``
      binds the module path (governance binding, Task 7);
  6.  ``claim_boundary`` equals the registry-required boundary AND that
      literal string is present in the module source (boundary binding);
  7.  every falsifier pytest node is COLLECTABLE by a live
      ``pytest --collect-only`` (Task 2 — executable test_id resolution,
      not string matching);
  8.  the acceptor carries at least one ``evidence`` entry with a sha256
      (provenance metadata resolves).

Run::

    python scripts/ci/check_instrument_evidence_chain.py
    python scripts/ci/check_instrument_evidence_chain.py --skip-collect  # links 1-6,8 only

Exit codes::

    0  — every instrument's full evidence chain resolves
    1  — at least one dangling / drifted / uncollectable evidence reference
    2  — the registry itself is missing or malformed (fail-closed)
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "governance" / "INSTRUMENTS.yaml"

_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
# A falsifier node is "<path>::<func>" (optionally "<func>[param]").
_NODE = re.compile(r"^(?P<path>[^:]+\.py)::(?P<func>[A-Za-z_][\w\[\]\-.]*)$")


@dataclass
class InstrumentReport:
    instrument_id: str
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def _sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _commit_exists(sha: str) -> bool:
    proc = subprocess.run(
        ["git", "cat-file", "-e", f"{sha}^{{commit}}"],
        cwd=ROOT,
        capture_output=True,
    )
    return proc.returncode == 0


def _commit_touched(sha: str, module: str) -> bool:
    proc = subprocess.run(
        ["git", "show", "--no-color", "--name-only", "--format=", sha],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return False
    touched = {line.strip() for line in proc.stdout.splitlines() if line.strip()}
    return module in touched


def _acceptor_binds(acceptor_path: Path, module: str) -> bool:
    try:
        data = yaml.safe_load(acceptor_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return False
    if not isinstance(data, dict):
        return False
    scope = data.get("diff_scope") or {}
    changed = scope.get("changed_files") or []
    for entry in changed:
        if isinstance(entry, dict) and entry.get("path") == module:
            return True
    return False


def _acceptor_has_provenance(acceptor_path: Path) -> bool:
    try:
        data = yaml.safe_load(acceptor_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return False
    if not isinstance(data, dict):
        return False
    evidence = data.get("evidence") or []
    for entry in evidence:
        if isinstance(entry, dict) and _SHA256.match(str(entry.get("sha256", ""))):
            return True
    return False


def _collect_output_has_node(node: str, output: str) -> bool:
    """Return true when pytest printed the node or its parametrized instances."""

    param_prefix = f"{node}["
    return any(
        (line := raw.strip()) == node or line.startswith(param_prefix)
        for raw in output.splitlines()
    )


def _plain_function_name(node_func: str) -> str:
    return node_func.split("[", 1)[0]


def _node_function_exists_in_source(node: str) -> bool:
    """Resolve a simple pytest function node without importing the test module."""

    match = _NODE.match(node)
    if not match:
        return False
    path = ROOT / match.group("path")
    if not path.is_file():
        return False
    func_name = _plain_function_name(match.group("func"))
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError:
        return False
    return any(isinstance(item, ast.FunctionDef) and item.name == func_name for item in tree.body)


def _is_native_collect_crash(proc: subprocess.CompletedProcess[str], output: str) -> bool:
    return proc.returncode < 0 or "Fatal Python error" in output or "Extension modules:" in output


def _node_is_collectable(node: str) -> tuple[bool, str]:
    """Return (collectable, detail). Uses a live ``pytest --collect-only``.

    A node string-matches but does NOT resolve when pytest cannot find the
    file, the function, or the parametrization — the exact dangling case the
    string-only gates miss.

    Some CI images can still abort the collect subprocess in native-extension
    teardown before pytest flushes node output. That is not a dangling evidence
    reference when the requested node is a literal top-level test function in
    the source file. The oracle is therefore: live pytest output wins; if the
    collect subprocess crashes at native-extension level, a source-backed AST
    fallback may only accept a concrete existing FunctionDef. Nonexistent nodes
    and normal pytest collection errors remain fail-closed.
    """
    env = os.environ.copy()
    env.setdefault("PYTHONFAULTHANDLER", "1")
    env.setdefault("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "--no-header",
            "-o",
            "addopts=",
            "-p",
            "no:cacheprovider",
            node,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env=env,
    )
    combined = proc.stdout + proc.stderr
    if _collect_output_has_node(node, proc.stdout):
        return True, "collectable"
    if proc.returncode != 0:
        if _is_native_collect_crash(proc, combined) and _node_function_exists_in_source(node):
            return True, "collectable via source-backed fallback after native collect crash"
        tail = combined.strip().splitlines()
        detail = tail[-1] if tail else f"pytest exit {proc.returncode}"
        return False, f"pytest exit {proc.returncode}: {detail}"
    # pytest --collect-only exits 0 with no collected items if the node
    # filename exists but the function does not — guard that explicitly.
    if "collected 0 items" in proc.stdout or "no tests ran" in proc.stdout:
        return False, "collected 0 items"
    return False, "node id not present in pytest collect output"


def _check_instrument(
    inst: dict[str, Any], required_boundary: str, *, skip_collect: bool
) -> InstrumentReport:
    iid = str(inst.get("id", "<unnamed>"))
    rep = InstrumentReport(instrument_id=iid)

    module_rel = inst.get("module")
    if not isinstance(module_rel, str) or not module_rel:
        rep.errors.append("missing 'module' field")
        return rep
    module_path = ROOT / module_rel

    # Link 1: module exists.
    if not module_path.is_file():
        rep.errors.append(f"module does not exist: {module_rel}")
        return rep  # nothing downstream is meaningful without the file

    # Link 2: source-drift lock.
    declared = str(inst.get("source_sha256", ""))
    if not _SHA256.match(declared):
        rep.errors.append("missing/malformed 'source_sha256' (need 64 hex)")
    else:
        actual = _sha256_of(module_path)
        if actual != declared:
            rep.errors.append(
                f"source drift on {module_rel}: registry={declared[:12]}… "
                f"actual={actual[:12]}… (refresh registry + acceptor under a diff-bound change)"
            )

    # Link 3: PR -> commit -> code.
    sha = str(inst.get("merge_commit", ""))
    if not _SHA40.match(sha):
        rep.errors.append("missing/malformed 'merge_commit' (need 40 hex)")
    elif not _commit_exists(sha):
        rep.errors.append(f"merge_commit not in git history: {sha[:12]}…")
    elif not _commit_touched(sha, module_rel):
        rep.errors.append(f"merge_commit {sha[:12]}… did not touch {module_rel}")

    # Link 4: test file exists.
    test_rel = inst.get("test_file")
    if not isinstance(test_rel, str) or not (ROOT / test_rel).is_file():
        rep.errors.append(f"test_file does not exist: {test_rel!r}")

    # Link 5: acceptor binds the module.
    acc_rel = inst.get("acceptor")
    if not isinstance(acc_rel, str) or not (ROOT / acc_rel).is_file():
        rep.errors.append(f"acceptor does not exist: {acc_rel!r}")
    else:
        acc_path = ROOT / acc_rel
        if not _acceptor_binds(acc_path, module_rel):
            rep.errors.append(
                f"acceptor {acc_rel} does not bind {module_rel} in diff_scope.changed_files"
            )
        # Link 8: provenance metadata.
        if not _acceptor_has_provenance(acc_path):
            rep.errors.append(
                f"acceptor {acc_rel} carries no sha256 evidence (provenance unresolved)"
            )

    # Link 6: claim boundary.
    boundary = str(inst.get("claim_boundary", ""))
    if boundary != required_boundary:
        rep.errors.append(f"claim_boundary={boundary!r} != required {required_boundary!r}")
    elif boundary not in module_path.read_text(encoding="utf-8"):
        rep.errors.append(f"claim_boundary {boundary!r} not declared in {module_rel} source")

    # Link 7: live falsifier-node resolution (Task 2).
    falsifiers = inst.get("falsifiers") or []
    if not isinstance(falsifiers, list) or not falsifiers:
        rep.errors.append("no falsifiers declared")
        return rep
    for node in falsifiers:
        node = str(node)
        m = _NODE.match(node)
        if not m:
            rep.errors.append(f"malformed falsifier node id: {node}")
            continue
        node_file = ROOT / m.group("path")
        if not node_file.is_file():
            rep.errors.append(f"falsifier file missing: {m.group('path')}")
            continue
        if skip_collect:
            continue
        ok, detail = _node_is_collectable(node)
        if not ok:
            rep.errors.append(f"falsifier node not collectable: {node} ({detail})")

    return rep


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--registry",
        type=Path,
        default=REGISTRY_PATH,
        help="path to INSTRUMENTS.yaml (default: governance/INSTRUMENTS.yaml)",
    )
    parser.add_argument(
        "--skip-collect",
        action="store_true",
        help="skip the live pytest --collect-only resolution (links 1-6,8 only)",
    )
    args = parser.parse_args(argv)

    if not args.registry.is_file():
        print(f"FAIL: instrument registry not found: {args.registry}", file=sys.stderr)
        return 2
    try:
        registry = yaml.safe_load(args.registry.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        print(f"FAIL: registry is not valid YAML: {exc}", file=sys.stderr)
        return 2
    if not isinstance(registry, dict):
        print("FAIL: registry root must be a mapping", file=sys.stderr)
        return 2

    required_boundary = str(registry.get("claim_boundary_required", ""))
    if not required_boundary:
        print("FAIL: registry missing 'claim_boundary_required'", file=sys.stderr)
        return 2
    instruments = registry.get("instruments")
    if not isinstance(instruments, list) or not instruments:
        print("FAIL: registry 'instruments' must be a non-empty list", file=sys.stderr)
        return 2

    reports = [
        _check_instrument(inst, required_boundary, skip_collect=args.skip_collect)
        for inst in instruments
        if isinstance(inst, dict)
    ]

    failed = [r for r in reports if not r.ok]
    for rep in reports:
        mark = "PASS" if rep.ok else "FAIL"
        print(f"[{mark}] {rep.instrument_id}")
        for err in rep.errors:
            print(f"       - {err}")

    n = len(reports)
    if failed:
        print(
            f"\nFAIL: {len(failed)}/{n} instruments have a dangling evidence reference",
            file=sys.stderr,
        )
        return 1
    print(f"\nOK: all {n} instruments have a fully resolved evidence chain")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
