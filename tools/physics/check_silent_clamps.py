# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Fail-closed scanner for silent numerical clamps in physics source.

Silent numerical clamps --- ``max(lam_max, 0.0)``, ``+ 1e-12`` epsilons,
``np.clip(x, lo, hi)`` saturations, implicit ``0.5 * (A + A.T)`` symmetrisation,
``np.abs(corr)`` sign-loss --- quietly repair physically invalid regimes. A
clamp is not wrong per se, but an *undeclared* clamp hides the boundary of
validity: when the input leaves the admissible set the code returns a plausible
number instead of failing or surfacing the repair. That is exactly the class of
defect that lets an invalid regime pass as a healthy one.

This checker enforces the numerical policy in ``docs/physics/numerical_policy.md``:
every clamp-shaped operation in the scoped physics tree MUST be bound to a named
entry in ``tools/physics/clamp_registry.yaml`` that declares its ``reason``,
``physical_meaning``, ``failure_mode``, ``test_ref`` and ``metadata_field``.

The scanner is *fail-closed* and *honest*: it does not silently pass on clamps it
cannot account for. Every clamp site in the scope roots that is NOT covered by a
registry entry is reported BY NAME (path:line) as an explicit violation, and the
process exits non-zero. The registry names its own governed surface rather than
implying full coverage.

Scoping is deliberately narrow to avoid false positives on legitimate non-clamp
code: only a closed set of AST-recognised clamp shapes is reported (see
``CLAMP_SHAPES``). Plain comparisons, bounded-domain math without a saturating
call, and arithmetic that does not match a clamp shape are ignored.

Usage::

    python tools/physics/check_silent_clamps.py            # human report
    python tools/physics/check_silent_clamps.py --json     # machine report

Exit code 0 iff every detected clamp site is registered; non-zero otherwise.
"""

from __future__ import annotations

import argparse
import ast
import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = REPO_ROOT / "tools" / "physics" / "clamp_registry.yaml"
POLICY_DOC = REPO_ROOT / "docs" / "physics" / "numerical_policy.md"

# Physics source roots the policy governs. Tests, research scratch and tooling
# are intentionally out of scope: the policy binds *production physics code*.
SCOPE_ROOTS: tuple[str, ...] = (
    "core/kuramoto",
    "core/physics",
    "core/indicators",
)
# Single-file scope members (ricci configuration lives outside the roots above).
SCOPE_FILES: tuple[str, ...] = ("core/config/kuramoto_ricci.py",)

# Required declaration fields on every registry clamp entry.
REQUIRED_ENTRY_FIELDS: tuple[str, ...] = (
    "name",
    "reason",
    "physical_meaning",
    "failure_mode",
    "test_ref",
    "metadata_field",
    "sites",
)

# Saturating / flooring numpy + builtin calls that constitute a clamp shape.
_CLAMP_CALLS: frozenset[str] = frozenset(
    {
        "clip",  # np.clip / ndarray.clip
        "maximum",  # np.maximum  (floor)
        "minimum",  # np.minimum  (cap)
        "nan_to_num",  # silent NaN/inf repair
        "clamp",  # generic
    }
)


@dataclass(frozen=True)
class ClampSite:
    """A single detected clamp-shaped operation."""

    path: str
    line: int
    shape: str
    snippet: str

    def key(self) -> str:
        return f"{self.path}:{self.line}"


def _scope_files() -> list[Path]:
    files: list[Path] = []
    for root in SCOPE_ROOTS:
        root_path = REPO_ROOT / root
        if root_path.is_dir():
            files.extend(sorted(root_path.rglob("*.py")))
    for rel in SCOPE_FILES:
        fp = REPO_ROOT / rel
        if fp.is_file():
            files.append(fp)
    return files


def _rel(path: Path) -> str:
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        # Path outside the repo root (e.g. a tmp file in a unit test): fall back
        # to the path as given so scan_file remains usable on arbitrary sources.
        return path.as_posix()


def _call_name(node: ast.Call) -> str | None:
    """Return the bare attribute/func name being called (e.g. ``clip``)."""
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return None


def _is_zero_or_eps(node: ast.expr) -> bool:
    """True for a literal 0, 0.0, or a tiny epsilon constant (< 1e-3)."""
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return abs(float(node.value)) < 1e-3
    # Unary minus on a small constant, e.g. -1e-12.
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return _is_zero_or_eps(node.operand)
    return False


def _is_small_eps(node: ast.expr) -> bool:
    """True for a strictly tiny positive epsilon literal (e.g. 1e-12, 1e-6)."""
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        v = float(node.value)
        return 0.0 < v < 1e-3
    return False


class _ClampVisitor(ast.NodeVisitor):
    """Collect clamp-shaped operations in a single module AST."""

    def __init__(self, path: str, source_lines: list[str]) -> None:
        self.path = path
        self.lines = source_lines
        self.sites: list[ClampSite] = []

    def _snippet(self, lineno: int) -> str:
        idx = lineno - 1
        if 0 <= idx < len(self.lines):
            return self.lines[idx].strip()
        return ""

    def _add(self, lineno: int, shape: str) -> None:
        self.sites.append(ClampSite(self.path, lineno, shape, self._snippet(lineno)))

    # --- saturating calls: np.clip / np.maximum / np.minimum / nan_to_num ---
    def visit_Call(self, node: ast.Call) -> None:
        name = _call_name(node)
        if name in _CLAMP_CALLS:
            shape = {
                "clip": "saturate_clip",
                "maximum": "floor_maximum",
                "minimum": "cap_minimum",
                "nan_to_num": "nan_repair",
                "clamp": "saturate_clip",
            }[name]
            self._add(node.lineno, shape)
        # builtin max(x, 0.0) / min(x, 0.0) floor or cap
        if name in {"max", "min"} and len(node.args) == 2:
            if any(_is_zero_or_eps(a) for a in node.args):
                self._add(
                    node.lineno,
                    "floor_builtin" if name == "max" else "cap_builtin",
                )
        # np.abs(corr...) sign loss: abs/np.abs applied to a name containing
        # 'corr' is a deliberate sign-discarding clamp on a signed quantity.
        if name == "abs" and len(node.args) == 1:
            arg = node.args[0]
            target = arg.value if isinstance(arg, ast.Subscript) else arg
            if isinstance(target, ast.Name) and "corr" in target.id.lower():
                self._add(node.lineno, "abs_sign_loss")
        self.generic_visit(node)

    # --- epsilon additions: <expr> + 1e-k  (denominator / log guards) ---
    def visit_BinOp(self, node: ast.BinOp) -> None:
        if isinstance(node.op, ast.Add):
            if _is_small_eps(node.right) or _is_small_eps(node.left):
                self._add(node.lineno, "epsilon_add")
        # implicit symmetrisation: 0.5 * (A + A.T)  /  (A + A.T) / 2
        self._maybe_symmetrise(node)
        self.generic_visit(node)

    def _maybe_symmetrise(self, node: ast.BinOp) -> None:
        # detect (X + X.T) sub-expression anywhere in a Mult/Div
        if not isinstance(node.op, (ast.Mult, ast.Div)):
            return
        for operand in (node.left, node.right):
            inner = operand
            if (
                isinstance(inner, ast.BinOp)
                and isinstance(inner.op, ast.Add)
                and _is_transpose_pair(inner.left, inner.right)
            ):
                self._add(node.lineno, "symmetrise")


def _is_transpose_pair(left: ast.expr, right: ast.expr) -> bool:
    """True for ``X + X.T`` where X is the same name on both sides."""
    if isinstance(left, ast.Name) and isinstance(right, ast.Attribute):
        return (
            right.attr == "T" and isinstance(right.value, ast.Name) and (right.value.id == left.id)
        )
    return False


# Closed set of detected shapes (for documentation / --json schema).
CLAMP_SHAPES: tuple[str, ...] = (
    "saturate_clip",
    "floor_maximum",
    "cap_minimum",
    "nan_repair",
    "floor_builtin",
    "cap_builtin",
    "abs_sign_loss",
    "epsilon_add",
    "symmetrise",
)


def scan_file(path: Path) -> list[ClampSite]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    visitor = _ClampVisitor(_rel(path), source.splitlines())
    visitor.visit(tree)
    # Deduplicate identical (line, shape) pairs produced by nested visits.
    seen: set[tuple[int, str]] = set()
    unique: list[ClampSite] = []
    for s in sorted(visitor.sites, key=lambda s: (s.line, s.shape)):
        if (s.line, s.shape) in seen:
            continue
        seen.add((s.line, s.shape))
        unique.append(s)
    return unique


def scan_tree() -> list[ClampSite]:
    sites: list[ClampSite] = []
    for fp in _scope_files():
        sites.extend(scan_file(fp))
    return sites


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
@dataclass
class RegistryError:
    entry: str
    message: str


def load_registry(path: Path = REGISTRY_PATH) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"clamp registry not found: {path}")
    with path.open(encoding="utf-8") as fh:
        data: Any = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a mapping at the top level")
    return data


def validate_registry_schema(registry: dict[str, Any]) -> list[RegistryError]:
    """Every entry must declare all required fields with non-empty values."""
    errors: list[RegistryError] = []
    entries = registry.get("clamps")
    if not isinstance(entries, list) or not entries:
        errors.append(RegistryError("<root>", "registry 'clamps' must be a non-empty list"))
        return errors
    seen_names: set[str] = set()
    for i, entry in enumerate(entries):
        label = f"clamps[{i}]"
        if not isinstance(entry, dict):
            errors.append(RegistryError(label, "entry must be a mapping"))
            continue
        name = entry.get("name")
        if isinstance(name, str) and name.strip():
            label = name
            if name in seen_names:
                errors.append(RegistryError(name, "duplicate clamp name"))
            seen_names.add(name)
        for fld in REQUIRED_ENTRY_FIELDS:
            val = entry.get(fld)
            if fld == "sites":
                if not isinstance(val, list) or not val:
                    errors.append(RegistryError(label, "'sites' must be a non-empty list"))
                continue
            if not isinstance(val, str) or not val.strip():
                errors.append(RegistryError(label, f"missing/empty field '{fld}'"))
    return errors


def registered_sites(registry: dict[str, Any]) -> dict[str, str]:
    """Map ``path:line`` -> clamp name for every declared site."""
    out: dict[str, str] = {}
    for entry in registry.get("clamps", []):
        if not isinstance(entry, dict):
            continue
        name = entry.get("name", "<unnamed>")
        for site in entry.get("sites", []) or []:
            if isinstance(site, str) and site.strip():
                out[site.strip()] = name
    return out


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
@dataclass
class ScanReport:
    sites: list[ClampSite]
    registered: dict[str, str]
    schema_errors: list[RegistryError]

    @property
    def unregistered(self) -> list[ClampSite]:
        return [s for s in self.sites if s.key() not in self.registered]

    @property
    def stale(self) -> list[str]:
        """Registered site keys that no longer correspond to a real clamp."""
        live = {s.key() for s in self.sites}
        return sorted(k for k in self.registered if k not in live)

    @property
    def ok(self) -> bool:
        return not self.schema_errors and not self.unregistered and not self.stale


def build_report() -> ScanReport:
    registry = load_registry()
    schema_errors = validate_registry_schema(registry)
    sites = scan_tree()
    return ScanReport(
        sites=sites,
        registered=registered_sites(registry),
        schema_errors=schema_errors,
    )


def _to_json(report: ScanReport) -> dict[str, Any]:
    return {
        "scope_roots": list(SCOPE_ROOTS),
        "scope_files": list(SCOPE_FILES),
        "shapes": list(CLAMP_SHAPES),
        "total_clamp_sites": len(report.sites),
        "registered_sites": len(report.registered),
        "schema_errors": [{"entry": e.entry, "message": e.message} for e in report.schema_errors],
        "unregistered": [
            {"path": s.path, "line": s.line, "shape": s.shape, "snippet": s.snippet}
            for s in report.unregistered
        ],
        "stale_registrations": report.stale,
        "ok": report.ok,
    }


def _print_human(report: ScanReport) -> None:
    print("silent-clamp policy scan")
    print(f"  scope            : {', '.join(SCOPE_ROOTS)}")
    print(f"  clamp sites found: {len(report.sites)}")
    print(f"  registered       : {len(report.registered)}")
    if report.schema_errors:
        print("\nREGISTRY SCHEMA ERRORS:")
        for e in report.schema_errors:
            print(f"  - [{e.entry}] {e.message}")
    if report.unregistered:
        print("\nUNREGISTERED CLAMPS (each must get a named policy entry + test):")
        for s in report.unregistered:
            print(f"  - {s.key()}  [{s.shape}]  {s.snippet}")
    if report.stale:
        print("\nSTALE REGISTRATIONS (no clamp at this site --- update registry):")
        for k in report.stale:
            print(f"  - {k}")
    print("\nRESULT:", "PASS" if report.ok else "FAIL")


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit machine report")
    args = parser.parse_args(list(argv) if argv is not None else None)
    report = build_report()
    if args.json:
        print(json.dumps(_to_json(report), indent=2, sort_keys=True))
    else:
        _print_human(report)
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
