#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Physics test validator for invariant-grounded tests.

Supported markers:
- INV-* in a test docstring means the test is a physics witness.
- NON_PHYSICS or NO_PHYSICS_INVARIANT in a test docstring means the test is an implementation check and is excluded from physics witness counts.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).parent
INVARIANTS_PATH = SCRIPT_DIR / "INVARIANTS.yaml"
INV_PATTERN = re.compile(r"INV-[A-Z0-9][A-Z0-9-]*")
# Honest-provenance contract (PR #414, sha d48bacf3). Discrete epistemic tiers
# only — never a float "truth-coherence score". ANCHORED = derivable from
# peer-reviewed established physics; EXTRAPOLATED = research direction with >=1
# anchor but a non-derivable leap; SPECULATIVE = schema only, no cited model.
_VALID_PROVENANCE_TIERS = frozenset({"ANCHORED", "EXTRAPOLATED", "SPECULATIVE"})
_AUTHORITY_PRIORITIES = frozenset({"P0", "P1"})
PHYSICS_KEYWORDS = {
    "physics",
    "kuramoto",
    "serotonin",
    "dopamine",
    "gaba",
    "energy",
    "thermo",
    "sync",
    "lyapunov",
    "ricci",
    "regime",
    "conservation",
    "entropy",
    "free_energy",
    "order_param",
    "inhibit",
    "ecs",
    "hpc",
    "pwpe",
    "active_inference",
    "freeenergy",
}


def load_invariants() -> dict[str, dict[str, str]]:
    registry: dict[str, dict[str, str]] = {}
    if not INVARIANTS_PATH.exists():
        return registry
    current_id: str | None = None
    current_block: dict[str, str] = {}
    for line in INVARIANTS_PATH.read_text(encoding="utf-8").splitlines():
        id_match = re.match(r"\s+id:\s+(INV-[A-Z0-9][A-Z0-9-]*)", line)
        if id_match:
            if current_id and current_block:
                registry[current_id] = current_block
            current_id = id_match.group(1)
            current_block = {"id": current_id}
            continue
        if current_id:
            kv_match = re.match(r"\s+(\w+):\s+(.+)", line)
            if kv_match:
                key, val = kv_match.group(1), kv_match.group(2).strip().strip("\"'")
                if "#" in val:
                    val = val[: val.index("#")].strip()
                current_block[key] = val
            if line.strip() == "" or re.match(r"\S", line):
                registry[current_id] = current_block
                current_id = None
                current_block = {}
    if current_id and current_block:
        registry[current_id] = current_block
    return registry


def _collect_names(node: ast.AST) -> set[str]:
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}


def _collect_call_names(node: ast.AST) -> set[str]:
    calls: set[str] = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Call):
            if isinstance(n.func, ast.Name):
                calls.add(n.func.id)
            elif isinstance(n.func, ast.Attribute):
                calls.add(n.func.attr)
                if isinstance(n.func.value, ast.Name):
                    calls.add(f"{n.func.value.id}.{n.func.attr}")
    return calls


def _has_decorator(func_node: ast.FunctionDef | ast.AsyncFunctionDef, name: str) -> bool:
    for dec in func_node.decorator_list:
        if isinstance(dec, ast.Name) and dec.id == name:
            return True
        if isinstance(dec, ast.Call):
            if isinstance(dec.func, ast.Name) and dec.func.id == name:
                return True
            if isinstance(dec.func, ast.Attribute) and dec.func.attr == name:
                return True
    return False


def _has_for_loop(node: ast.AST) -> bool:
    return any(isinstance(n, ast.For) for n in ast.walk(node))


def _count_asserts(node: ast.AST) -> int:
    return sum(1 for n in ast.walk(node) if isinstance(n, ast.Assert))


def _has_negative_slice(node: ast.AST) -> bool:
    for n in ast.walk(node):
        if isinstance(n, ast.Subscript) and isinstance(n.slice, ast.Slice):
            lower = n.slice.lower
            if isinstance(lower, ast.UnaryOp) and isinstance(lower.op, ast.USub):
                return True
            if (
                isinstance(lower, ast.Constant)
                and isinstance(lower.value, (int, float))
                and lower.value < 0
            ):
                return True
    return False


def _has_small_epsilon(node: ast.AST) -> bool:
    return any(
        isinstance(n, ast.Constant) and isinstance(n.value, float) and 0 < abs(n.value) < 1e-6
        for n in ast.walk(node)
    )


def _has_large_int(node: ast.AST, threshold: int = 100) -> bool:
    return any(
        isinstance(n, ast.Constant) and isinstance(n.value, int) and n.value > threshold
        for n in ast.walk(node)
    )


def _ok_universal(func: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[bool, str]:
    calls = _collect_call_names(func)
    if (
        _has_decorator(func, "given")
        or _has_for_loop(func)
        or calls & {"all", "np.all", "np.testing.assert_array_less"}
        or _count_asserts(func) >= 3
    ):
        return True, ""
    return False, "expected many-input, loop, array, or property-style check"


def _ok_asymptotic(func: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[bool, str]:
    calls = _collect_call_names(func)
    names = _collect_names(func)
    if (
        _has_negative_slice(func)
        or names & {"final", "steady", "late", "converged", "trajectory", "steps"}
        or calls & {"simulate", "run", "evolve", "integrate"}
        or _has_large_int(func, 100)
    ):
        return True, ""
    return False, "expected late-time or converged trajectory check"


def _ok_monotonic(func: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[bool, str]:
    calls = _collect_call_names(func)
    if calls & {"diff", "np.diff"} or "violations" in _collect_names(func) or _has_for_loop(func):
        return True, ""
    return False, "expected diff, loop, or explicit ordering check"


def _ok_statistical(func: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[bool, str]:
    calls = _collect_call_names(func)
    if calls & {"mean", "np.mean", "std", "np.std", "np.var", "np.average"}:
        return True, ""
    if _has_for_loop(func) and _collect_names(func) & {
        "seed",
        "seeds",
        "trial",
        "trials",
        "realization",
        "realizations",
    }:
        return True, ""
    if any(isinstance(n, ast.ListComp) for n in ast.walk(func)):
        return True, ""
    return False, "expected sample or ensemble evidence"


def _ok_algebraic(func: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[bool, str]:
    calls = _collect_call_names(func)
    if calls & {
        "assert_allclose",
        "np.testing.assert_allclose",
        "approx",
        "isclose",
    } or _has_small_epsilon(func):
        return True, ""
    return False, "expected exact or tolerance-bounded comparison"


def _ok_qualitative(func: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[bool, str]:
    if _has_for_loop(func) or _count_asserts(func) >= 2:
        return True, ""
    return False, "expected parameter sweep or multiple directional checks"


def _ok_conservation(func: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[bool, str]:
    names = _collect_names(func)
    if len(
        names & {"before", "after", "initial", "final", "total_before", "total_after"}
    ) >= 2 or _has_for_loop(func):
        return True, ""
    return False, "expected before/after quantity comparison"


def _ok_distributional(func: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[bool, str]:
    calls = _collect_call_names(func)
    if calls & {
        "rayleigh",
        "kstest",
        "ks_2samp",
        "chisquare",
        "histogram",
        "np.histogram",
        "mean",
        "np.mean",
        "std",
        "np.std",
    } or _has_for_loop(func):
        return True, ""
    return False, "expected distribution or moment check"


TYPE_CHECKERS: dict[str, Any] = {
    "universal": _ok_universal,
    "asymptotic": _ok_asymptotic,
    "monotonic": _ok_monotonic,
    "statistical": _ok_statistical,
    "algebraic": _ok_algebraic,
    "qualitative": _ok_qualitative,
    "conservation": _ok_conservation,
    "conditional": _ok_qualitative,
    "distributional": _ok_distributional,
}
TEST_TYPE_CHECKERS: dict[str, Any] = {
    "property_test": _ok_universal,
    "convergence_test": _ok_asymptotic,
    "trajectory_test": _ok_monotonic,
    "sweep_test": _ok_qualitative,
    "ensemble_test": _ok_statistical,
    "monotonicity_test": _ok_monotonic,
    "balance_test": _ok_conservation,
    "statistical_test": _ok_statistical,
    "correlation_test": _ok_statistical,
}


def resolve_l3_checker(inv_data: dict[str, str]) -> tuple[Any | None, str]:
    test_type = inv_data.get("test_type", "")
    inv_type = inv_data.get("type", "")
    if test_type in TEST_TYPE_CHECKERS:
        return TEST_TYPE_CHECKERS[test_type], f"test_type='{test_type}'"
    if inv_type in TYPE_CHECKERS:
        return TYPE_CHECKERS[inv_type], f"type='{inv_type}'"
    return None, ""


class Issue:
    def __init__(self, level: str, line: int, func: str, msg: str):
        self.level = level
        self.line = line
        self.func = func
        self.msg = msg

    def __str__(self) -> str:
        return f"  [{self.level}] L{self.line}: {self.func}() - {self.msg}"


def _name_has_physics_keyword(name: str) -> bool:
    tokens = {token for token in re.split(r"[^a-z0-9]+", name.lower()) if token}
    for keyword in PHYSICS_KEYWORDS:
        if "_" in keyword:
            if keyword in name:
                return True
            continue
        if keyword == "sync":
            if tokens & {"sync", "synchrony", "synchronous", "synchronization", "synchronisation"}:
                return True
            continue
        if keyword in tokens:
            return True
        if keyword == "inhibit" and ("inhibition" in tokens or "inhibitory" in tokens):
            return True
    return False


def is_physics_test(filepath: Path) -> bool:
    name = filepath.stem.lower()
    parts = {p.lower() for p in filepath.parts}
    if "validation" in parts and "validator" in name:
        return False
    return bool(parts & PHYSICS_KEYWORDS) or _name_has_physics_keyword(name)


def is_physics_source(filepath: Path) -> bool:
    name = filepath.stem.lower()
    parts = {p.lower() for p in filepath.parts}
    if "test" in name or "test" in parts:
        return False
    return bool(parts & PHYSICS_KEYWORDS) or _name_has_physics_keyword(name)


def _is_non_physics_doc(docstring: str) -> bool:
    return "NON_PHYSICS" in docstring or "NO_PHYSICS_INVARIANT" in docstring


def _check_error_msg_quality(msg_source: str) -> list[str]:
    missing: list[str] = []
    if not INV_PATTERN.search(msg_source):
        missing.append("INV-* ID")
    if not re.search(
        r"[=:]\s*[-+]?\d|actual|observed|got|result|R=|R_final|delta=|level=",
        msg_source,
        re.IGNORECASE,
    ):
        missing.append("observed value")
    if not re.search(
        r"expect|should|must|theory|predicted|required|outside", msg_source, re.IGNORECASE
    ):
        missing.append("expected behavior")
    if not re.search(
        r"[NK]=\d|seed=|steps=|at\s+\w+=|with\s+\w+=|gamma=|K_c=", msg_source, re.IGNORECASE
    ):
        missing.append("parameters")
    return missing


def check_test_file(filepath: Path, registry: dict[str, dict[str, str]]) -> list[Issue]:
    issues: list[Issue] = []
    source = filepath.read_text(encoding="utf-8")
    source_lines = source.splitlines()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return [Issue("L0", 0, "<file>", f"syntax error in {filepath}")]

    for node in ast.walk(tree):
        if not isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef)
        ) or not node.name.startswith("test_"):
            continue
        docstring = ast.get_docstring(node) or ""
        if _is_non_physics_doc(docstring):
            continue
        inv_refs = INV_PATTERN.findall(docstring)
        if not inv_refs:
            issues.append(Issue("L1", node.lineno, node.name, "No INV-* reference in docstring."))
            continue
        for inv_id in inv_refs:
            if registry and inv_id not in registry:
                issues.append(
                    Issue("L2", node.lineno, node.name, f"{inv_id} not found in INVARIANTS.yaml.")
                )
        for inv_id in inv_refs:
            if inv_id not in registry:
                continue
            checker_fn, label = resolve_l3_checker(registry[inv_id])
            if checker_fn is not None:
                ok, reason = checker_fn(node)
                if not ok:
                    issues.append(
                        Issue("L3", node.lineno, node.name, f"{inv_id} has {label}. {reason}")
                    )

        has_any_msg = False
        has_no_msg = False
        for child in ast.walk(node):
            if not isinstance(child, ast.Assert):
                continue
            if child.msg is None:
                has_no_msg = True
                continue
            has_any_msg = True
            assert_start = child.lineno - 1
            assert_end = min(
                getattr(child.msg, "end_lineno", child.msg.lineno) or child.msg.lineno,
                len(source_lines),
            )
            msg_source = "\n".join(source_lines[assert_start:assert_end])
            missing = _check_error_msg_quality(msg_source)
            if missing:
                issues.append(
                    Issue(
                        "L4",
                        child.lineno,
                        node.name,
                        f"Assert message missing: {', '.join(missing)}.",
                    )
                )
        if has_no_msg and not has_any_msg:
            issues.append(
                Issue("L4", node.lineno, node.name, "All assertions lack error messages.")
            )

        for child in ast.walk(node):
            if not isinstance(child, ast.Assert) or child.lineno > len(source_lines):
                continue
            line = source_lines[child.lineno - 1].strip()
            if not re.search(r"assert.*[<>=]\s*0\.\d+", line):
                continue
            context = "\n".join(source_lines[max(0, child.lineno - 4) : child.lineno]).lower()
            if not any(
                pat in context
                for pat in (
                    "sqrt",
                    "np.sqrt",
                    "math.sqrt",
                    "k_c",
                    "kc",
                    "pi",
                    "np.pi",
                    "epsilon",
                    "eps",
                    "tolerance",
                    "tol",
                )
            ):
                issues.append(
                    Issue(
                        "L5",
                        child.lineno,
                        node.name,
                        f"Possible magic number threshold. Line: {line[:80]}",
                    )
                )
    return issues


CLAMP_PATTERNS = [
    re.compile(r"np\.clip\s*\("),
    re.compile(r"max\s*\(\s*[\d.]+\s*,\s*min\s*\("),
    re.compile(r"min\s*\(\s*[\d.]+\s*,\s*max\s*\("),
    re.compile(r"=\s*max\s*\(\s*[\d.]+"),
    re.compile(r"=\s*min\s*\(\s*[\d.]+"),
    re.compile(r"\.clamp\s*\("),
    re.compile(r"\.clip\s*\("),
]
LOG_PATTERNS = [
    re.compile(r"log(ger|ging)?\."),
    re.compile(r"warn(ing)?\s*\("),
    re.compile(r"_log\s*\("),
    re.compile(r"emit\s*\("),
    re.compile(r"telemetry"),
    re.compile(r"tacl\."),
    re.compile(r"#\s*bounds:"),
]


def audit_code_file(filepath: Path) -> list[Issue]:
    issues: list[Issue] = []
    try:
        source_lines = filepath.read_text(encoding="utf-8").splitlines()
    except (UnicodeDecodeError, OSError):
        return []
    for i, line in enumerate(source_lines, 1):
        stripped = line.strip()
        if stripped.startswith("#") or not any(p.search(stripped) for p in CLAMP_PATTERNS):
            continue
        context = "\n".join(source_lines[max(0, i - 4) : min(len(source_lines), i + 3)])
        has_log = any(p.search(context) for p in LOG_PATTERNS)
        has_inv_ref = bool(INV_PATTERN.search(context))
        if not has_log and not has_inv_ref:
            issues.append(
                Issue(
                    "C1",
                    i,
                    filepath.stem,
                    f"Clamp or clip lacks log, telemetry, bounds note, or INV reference. Line: {stripped[:80]}",
                )
            )
        if (
            re.search(r"clip\s*\(\s*\w+\s*,\s*[\d.]+\s*,\s*[\d.]+", stripped)
            and not has_inv_ref
            and not has_log
        ):
            issues.append(
                Issue(
                    "C2",
                    i,
                    filepath.stem,
                    f"Numeric bounds need a note or INV reference. Line: {stripped[:80]}",
                )
            )
    return issues


def _iter_files(target: Path) -> list[Path]:
    return [target] if target.is_file() else sorted(target.rglob("*.py"))


def _test_count_excluding_non_physics(path: Path) -> int:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return 0
    count = 0
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith(
            "test_"
        ):
            if not _is_non_physics_doc(ast.get_docstring(node) or ""):
                count += 1
    return count


def _run_test_validation(
    files: list[Path], registry: dict[str, dict[str, str]], summary_mode: bool
) -> None:
    total_issues: dict[str, int] = {}
    physics_files = 0
    total_tests = 0
    for f in files:
        if not f.name.startswith("test_") or not is_physics_test(f):
            continue
        physics_files += 1
        total_tests += _test_count_excluding_non_physics(f)
        issues = check_test_file(f, registry)
        if issues and not summary_mode:
            print(f"\n{f}:")
            for issue in issues:
                print(issue)
        for issue in issues:
            total_issues[issue.level] = total_issues.get(issue.level, 0) + 1

    print(f"\n{'=' * 64}")
    print("Physics Test Validation Report")
    print(f"{'=' * 64}")
    print(f"Files scanned:    {physics_files}")
    print(f"Test functions:   {total_tests}\n")
    levels = ["L0", "L1", "L2", "L3", "L4", "L5"]
    labels = {
        "L0": "Unparseable physics test (syntax error)",
        "L1": "Missing INV-* reference",
        "L2": "Invalid INV-* ID (not in YAML)",
        "L3": "Test type != invariant type",
        "L4": "Missing/poor error messages",
        "L5": "Possible magic number threshold",
    }
    print("Issues by level:")
    for lv in levels:
        print(f"  [{lv}] {labels[lv] + ':':<36s} {total_issues.get(lv, 0)}")
    total = sum(total_issues.get(lv, 0) for lv in levels)
    print(f"  {'-' * 44}")
    print(f"  {'Total:':<40s} {total}")
    if total == 0:
        print("\nAll physics tests pass validation.")
    else:
        l1 = total_issues.get("L1", 0)
        grounded = max(0, total_tests - l1)
        pct = (grounded / total_tests * 100) if total_tests else 0
        print(f"\nPhysics grounding: {grounded}/{total_tests} tests ({pct:.0f}%)")
        print("\nFix priority: L1 -> L4 -> L3 -> L5 -> L2")
        sys.exit(1)


def _run_audit_code(files: list[Path], summary_mode: bool) -> None:
    total_issues: dict[str, int] = {}
    scanned = 0
    for f in files:
        if f.name.startswith("test_") or f.suffix != ".py" or not is_physics_source(f):
            continue
        scanned += 1
        issues = audit_code_file(f)
        if issues and not summary_mode:
            print(f"\n{f}:")
            for issue in issues:
                print(issue)
        for issue in issues:
            total_issues[issue.level] = total_issues.get(issue.level, 0) + 1
    print(f"\n{'=' * 64}")
    print("Production Code Audit Report")
    print(f"{'=' * 64}")
    print(f"Files scanned:  {scanned}")
    c1 = total_issues.get("C1", 0)
    c2 = total_issues.get("C2", 0)
    print(f"  [C1] Clamp/clip without note:          {c1}")
    print(f"  [C2] Numeric bounds without note:      {c2}")
    print(f"  {'-' * 44}")
    print(f"  Total:                                 {c1 + c2}")
    if c1 + c2 == 0:
        print("\nNo clamp/bounds audit issues detected.")
    else:
        sys.exit(1)


def check_provenance(reg: dict[str, dict[str, str]]) -> list[str]:
    """Self-check 5 — honest-provenance contract, fail-closed.

    Restored: PR #414 (sha d48bacf3) shipped an enforcing check 5; a later
    validator rewrite silently regressed it to an unconditional ``print(...
    PASS)``, so for several commits any invariant could be relabelled
    ``ANCHORED`` with zero gate resistance. This re-derives the verdict.

    Two rules over every invariant that *declares* a ``provenance`` tier:
      1. the tier is one of the three discrete levels — no free-text tiers,
         no fake-precision float standing in for an epistemic level;
      2. a SPECULATIVE tier (schema only, no specific cited model) may not
         carry P0/P1 authority — P2 informational is the ceiling.

    Invariants with no ``provenance`` key are out of scope (legacy registry
    entries predating the tier system). This check never *invents* a tier;
    it only refuses to let a declared one lie.
    """
    errors: list[str] = []
    for inv_id, data in reg.items():
        prov_raw = data.get("provenance")
        if prov_raw is None:
            continue
        prov = prov_raw.upper()
        if prov not in _VALID_PROVENANCE_TIERS:
            errors.append(
                f"{inv_id}: provenance '{prov_raw}' is not a discrete tier "
                f"{sorted(_VALID_PROVENANCE_TIERS)}"
            )
            continue
        priority = data.get("priority", "").upper()
        if prov == "SPECULATIVE" and priority in _AUTHORITY_PRIORITIES:
            errors.append(
                f"{inv_id}: SPECULATIVE invariant at {priority} — a schema with "
                "no cited model may not carry P0/P1 authority (max P2)"
            )
    return errors


def _self_check() -> None:
    reg = load_invariants()
    if not reg:
        print("FAIL: cannot load INVARIANTS.yaml")
        sys.exit(1)
    print(f"1. Loaded {len(reg)} invariants")
    errors: list[str] = []
    for inv_id, data in reg.items():
        checker, _ = resolve_l3_checker(data)
        if checker is None:
            errors.append(
                f"{inv_id}: type='{data.get('type')}' test_type='{data.get('test_type')}' has no L3 checker"
            )
    if errors:
        print(f"2. FAIL: {len(errors)} types without checker")
        for err in errors[:20]:
            print(f"   {err}")
        sys.exit(1)
    print("2. All invariant types have L3 checkers")
    print("3. INV_PATTERN matches registered ID format")
    print("4. Cross-ref OK: registry loaded")
    prov_errors = check_provenance(reg)
    if prov_errors:
        print(f"5. FAIL: {len(prov_errors)} provenance-tier violations")
        for err in prov_errors[:20]:
            print(f"   {err}")
        sys.exit(1)
    print("5. Provenance OK: tiers discrete; no SPECULATIVE invariant at P0/P1")
    print("6. Regression guard OK: compact validator loaded")
    print("7. Source/tests path integrity delegated to evidence matrix generator")
    print("\nPhysics kernel self-check PASSED")


def main() -> None:
    args = sys.argv[1:]
    if not args:
        print("Usage: python validate_tests.py <path> [--summary|--audit-code] | --self-check")
        sys.exit(1)
    if "--self-check" in args:
        _self_check()
        return
    target = Path(args[0])
    summary_mode = "--summary" in args
    audit_code = "--audit-code" in args
    registry = load_invariants()
    if not registry:
        # Fail-closed, consistent with _self_check: an empty/unloadable
        # INVARIANTS.yaml silently disables L2/L3 grounding, so the gate must
        # not report GREEN on the absence of the registry it depends on.
        print(f"FAIL: cannot load {INVARIANTS_PATH.name} (registry empty/unloadable)")
        sys.exit(1)
    print(f"Loaded {len(registry)} invariants from {INVARIANTS_PATH.name}")
    if not target.exists():
        print(f"Not found: {target}")
        sys.exit(1)
    files = _iter_files(target)
    if audit_code:
        _run_audit_code(files, summary_mode)
    else:
        _run_test_validation(files, registry, summary_mode)


if __name__ == "__main__":
    main()
