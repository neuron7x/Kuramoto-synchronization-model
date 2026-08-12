#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Every module and path a config NAMES must exist IN THIS REPOSITORY.

This gate exists because of a specific failure, not a general principle.

``configs/templates/backtest.yaml.j2`` declared::

    entrypoint: core.strategies.signals:moving_average_signal

ADR-0024 retired the top-level ``core/`` package, so that module is gone from
this tree. The CLI resolves the entrypoint with ``importlib.import_module``.
Importlib does not fail closed on a name this repository no longer defines --
it searches ``sys.path``. On the developer's machine it found the ``core/``
package of a *different project* on disk and imported that. ``geosync backtest``
and ``geosync optimize`` were loading and executing a foreign repository's code.
The visible symptom was an unrelated-looking ``Duplicated timeseries in
CollectorRegistry``, because that project registers the same ``geosync_*``
Prometheus metrics -- the true fault (executing someone else's code) was
invisible.

The lesson generalises past that one string: **a config that names a module is
making an existence claim, and nothing was checking it.** A missing name does
not raise -- it silently binds to whatever else answers to it. So the question
this gate asks is not "does this module import?" (the broken entrypoint DID
import) but "does it resolve to a file inside this repository?".

Three rules, deliberately narrow so that a RED here is always a real defect:

  R1 entrypoint resolution
      ``entrypoint:`` / ``objective:`` values of the form ``module:callable``
      must resolve to a module file *under the repo root* AND that module must
      actually define the callable. Resolution is done by walking the package
      path on disk -- never by importing, which is what let the foreign package
      in.

  R2 declared roots exist
      ``scan_roots`` / ``paths`` / ``import_roots`` name directories or modules
      that the architecture contract claims to own. A root that does not exist
      owns nothing, and a gate keyed on it silently checks nothing.

  R3 the stale twin
      A path literal that does NOT exist, while ``geosync/<that same path>``
      DOES, is a path the ADR-0024 move left behind. This is how the d002g
      acceptor came to fence ``application/governance/claim_ledger.py`` after
      the file had become ``geosync/application/governance/claim_ledger.py``:
      the forbidden-paths fence stopped protecting the file it named, and said
      nothing. ``forbidden_paths`` is NOT checked for mere existence -- a
      prohibition may legitimately name a path that must never appear -- but a
      prohibition whose target simply MOVED is a disarmed fence, and the twin
      test detects exactly that, with no false positives.

FALSIFICATION: revert any of the three fix commits (templates / connectome /
d002g acceptor) and this gate must go RED. If it stays GREEN, it is decorative.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Config surfaces that name modules or repo paths.
SCAN_GLOBS: tuple[str, ...] = (
    "configs/**/*.yaml",
    "configs/**/*.yml",
    "configs/**/*.j2",
    ".claude/commit_acceptors/*.yaml",
    "docs/architecture/connectome.yaml",
)

#: Fields whose value is ``module:callable``.
_ENTRYPOINT_RE = re.compile(
    r"^\s*(?:entrypoint|objective)\s*:\s*[\"']?([A-Za-z_][\w.]*):([\w.]+)[\"']?\s*$"
)

#: Fields that declare a root this repository claims to own.
_ROOT_FIELDS = ("scan_roots", "paths", "import_roots")

#: A bare list item that looks like a repo path (``- "a/b/c.py"``).
_LIST_PATH_RE = re.compile(r"^\s*-\s*[\"']?([A-Za-z_][\w./-]*\.(?:py|yaml|yml|json|md))[\"']?\s*$")
_LIST_DIR_RE = re.compile(r"^\s*-\s*[\"']?([A-Za-z_][\w./-]*[^/.\s\"'])[\"']?\s*$")

#: Prohibitions may name a path that must never exist -- existence is not required.
#: They are still subject to R3 (the twin test).
_PROHIBITION_FIELDS = ("forbidden_paths", "forbidden_imports")

#: Artefacts pinned byte-for-byte by the D-002G non-mutation contract
#: (tests/systemic_risk/test_d002g_m2_locked_governance_untouched.py). Their sha256 is
#: asserted, so they CANNOT be repaired -- and must not be.
#:
#: A pre-registration artefact is a historical record of what was promised BEFORE the
#: result was known. Rewriting its paths to match a later repository layout would
#: falsify the very record it exists to preserve, and the sha256 lock is there to make
#: that impossible. So a dangling reference inside one of these is not a defect to fix;
#: it is a frozen fact about a tree that no longer exists.
#:
#: This exemption is the one place the gate yields, so it is itself gated: a test
#: asserts this tuple equals the locked set the sha256 contract pins, and fails if the
#: two ever drift. An exemption nobody checks is a hole.
_FROZEN_ARTEFACTS: frozenset[str] = frozenset(
    {
        ".claude/commit_acceptors/x10r-d002g-nondegenerate-null-redesign.yaml",
        ".claude/commit_acceptors/x10r-d002g-p1-implementation.yaml",
        ".claude/commit_acceptors/x10r-d002g-p1-strike-scaffolding.yaml",
        "docs/governance/D002C_ATTEMPT_2_NULL_AUDIT_FALSIFICATION_REPORT.md",
        "docs/governance/D002C_CANONICAL_RUN_REPORT.md",
        "docs/governance/D002C_CLAIM_LEDGER.yaml",
        "docs/governance/D002C_PREREGISTRATION.yaml",
        "docs/governance/D002G_ACCEPTANCE_RULES.md",
        "docs/governance/D002G_NONDEGENERATE_NULL_DESIGN.md",
        "docs/governance/D002G_PREREGISTRATION.yaml",
    }
)


def _resolve_module_on_disk(dotted: str) -> Path | None:
    """Resolve ``a.b.c`` to a file under REPO_ROOT, WITHOUT importing it.

    Importing is precisely what admitted the foreign package: ``import_module``
    consults sys.path, so a name this repo no longer defines resolves to any
    other project that happens to define it. Walking the tree cannot do that.
    """
    rel = Path(*dotted.split("."))
    for candidate in (REPO_ROOT / rel.with_suffix(".py"), REPO_ROOT / rel / "__init__.py"):
        if candidate.is_file():
            return candidate
    return None


def _defines(module_file: Path, attr: str) -> bool:
    """Does ``module_file`` define ``attr`` at top level? Parsed, never executed."""
    import ast

    root = attr.split(".")[0]
    try:
        tree = ast.parse(module_file.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return False
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name == root:
                return True
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == root:
                    return True
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for a in node.names:
                if (a.asname or a.name.split(".")[0]) == root:
                    return True
    return False


def _root_exists(rel: str) -> bool:
    """A declared root resolves to a directory, a module file, or a package."""
    base = REPO_ROOT / rel
    return base.exists() or base.with_suffix(".py").is_file() or (base / "__init__.py").is_file()


def _twin_exists(rel: str) -> bool:
    """R3: the path is gone, but ``geosync/<path>`` is there -- the move left it behind."""
    return not (REPO_ROOT / rel).exists() and (REPO_ROOT / "geosync" / rel).exists()


def _scan_file(path: Path) -> list[str]:
    violations: list[str] = []
    rel_file = path.relative_to(REPO_ROOT)
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()

    field: str | None = None
    for lineno, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        # R1 -- entrypoint resolution
        m = _ENTRYPOINT_RE.match(line)
        if m:
            dotted, attr = m.group(1), m.group(2)
            module_file = _resolve_module_on_disk(dotted)
            if module_file is None:
                violations.append(
                    f"{rel_file}:{lineno}: R1 entrypoint `{dotted}:{attr}` does not resolve "
                    f"to any module in this repository. importlib will NOT fail on this -- it "
                    f"will search sys.path and may import another project's `{dotted.split('.')[0]}`."
                )
            elif not _defines(module_file, attr):
                violations.append(
                    f"{rel_file}:{lineno}: R1 module `{dotted}` resolves to "
                    f"{module_file.relative_to(REPO_ROOT)} but does not define `{attr}`"
                )
            continue

        # track which field a list belongs to
        if stripped.endswith(":") and not stripped.startswith("-"):
            field = stripped[:-1].strip().strip('"').strip("'")
            continue

        if not stripped.startswith("-"):
            if ":" in stripped:
                field = None
            continue

        item = _LIST_PATH_RE.match(line) or _LIST_DIR_RE.match(line)
        if not item:
            continue
        value = item.group(1)
        if "/" not in value and not value.endswith(".py"):
            continue  # bare token (a domain name, a package alias) -- not a repo path

        # R3 -- the stale twin. Applies to EVERY path-bearing field, prohibitions included.
        if _twin_exists(value):
            violations.append(
                f"{rel_file}:{lineno}: R3 `{value}` does not exist, but "
                f"`geosync/{value}` does. The ADR-0024 move left this reference behind"
                + (
                    " -- a prohibition whose target moved is a disarmed fence."
                    if field in _PROHIBITION_FIELDS
                    else "."
                )
            )
            continue

        # R2 -- declared roots must exist. Prohibitions are exempt (see module docstring).
        # A root may name a directory OR a module: `import_roots` legitimately carries
        # `geosync/neural_controller/core/sensory`, which is `sensory.py` on disk.
        if field in _ROOT_FIELDS and not _root_exists(value):
            violations.append(
                f"{rel_file}:{lineno}: R2 declared root `{value}` (under `{field}`) does not "
                f"exist. A contract keyed on a root that is not there enforces nothing."
            )

    return violations


def main() -> int:
    files: list[Path] = []
    for pattern in SCAN_GLOBS:
        files.extend(sorted(REPO_ROOT.glob(pattern)))

    violations: list[str] = []
    skipped_frozen = 0
    for f in files:
        if not f.is_file():
            continue
        if f.relative_to(REPO_ROOT).as_posix() in _FROZEN_ARTEFACTS:
            skipped_frozen += 1
            continue
        violations.extend(_scan_file(f))

    if violations:
        print(f"[-] config-reference gate RED: {len(violations)} dangling reference(s)\n")
        for v in violations:
            print(f"  {v}")
        print(
            "\nA config that names a module or a path is making an existence claim. "
            "Fix the reference, or delete it."
        )
        return 1

    print(
        f"[+] config-reference gate GREEN: {len(files) - skipped_frozen} config files "
        f"(+{skipped_frozen} sha256-frozen, exempt), every named module and path resolves in-repo"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
