# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Executable-falsifier resolution gate for the seven-physics line.

INV-* invariants that declare a ``falsifier_test`` in
``.claude/physics/INVARIANTS.yaml`` assert more than a prose
falsification clause: they name *the exact pytest node that fails if
the physics is violated*. Doctrine (CLAUDE.md / FORBIDDEN_CLAIMS):
"No falsifier means no claim. No replay means no claim." A falsifier
must be EXECUTABLE — it must resolve to a real pytest node that
actually runs and can actually fail.

This module is the teeth. For every invariant carrying a
``falsifier_test`` binding it proves, structurally:

  1. the bound test file exists,
  2. the named function is a defined ``test_*`` node (AST resolution —
     not a prose pointer, a *collectable* node),
  3. the function body references the invariant id it falsifies, so
     the binding cannot drift to an unrelated test, and
  4. the function genuinely exercises a *violation* path (asserts the
     ``is_*_consistent``/``ruled_out``/``within_budget`` verdict flips
     to the failing side), so a vacuous ``assert True`` cannot satisfy
     the gate.

These tests have NO physics invariant of their own; they are an
integrity check on the falsifier registry surface.

NON_PHYSICS
"""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
from typing import Any, cast

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
PHYSICS_DIR = REPO_ROOT / ".claude" / "physics"


def _load_invariant_registry() -> dict[str, dict[str, Any]]:
    """Load the invariant registry via the un-packaged ``.claude/physics``
    validator.

    The validator lives outside any importable package, so it is loaded by
    file location. We deliberately avoid mutating ``sys.path`` and importing
    the symbol at module top: that pattern forces an ``E402`` violation and an
    inline lint suppression, which the architecture debt ratchet (rightly)
    refuses to let grow. ``importlib`` keeps the binding suppression-free.
    """
    spec = importlib.util.spec_from_file_location(
        "physics_validate_tests", PHYSICS_DIR / "validate_tests.py"
    )
    if spec is None or spec.loader is None:  # pragma: no cover - import wiring
        raise RuntimeError(f"cannot load validator at {PHYSICS_DIR / 'validate_tests.py'}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return cast("dict[str, dict[str, Any]]", module.load_invariants())

# Invariants in the seven-physics line whose tier is below ANCHORED and
# whose node-level falsifier binding is enforced here. ANCHORED-tier
# invariants (ARROW, BEKENSTEIN, ANCHORED-SUBSTRATE-GATE) carry their
# node-level falsifiers through docs/CLAIMS.yaml + compute_fps_audit and
# the substrate-gate integration chain; this module covers the
# EXTRAPOLATED/SPECULATIVE ones that no other node-resolving gate reaches.
_EXPECTED_FALSIFIER_INVARIANTS = frozenset(
    {
        "INV-COSMOLOGICAL-COMPUTE",
        "INV-JACOBSON-OBSERVER",
        "INV-SIMULATION-FALSIFICATION",
        "INV-OBSERVER-BANDWIDTH",
    }
)


def _invariants_with_falsifier() -> dict[str, str]:
    """Map invariant-id -> declared ``falsifier_test`` node id."""
    registry = _load_invariant_registry()
    return {
        inv_id: data["falsifier_test"]
        for inv_id, data in registry.items()
        if data.get("falsifier_test")
    }


_FALSIFIER_BINDINGS = _invariants_with_falsifier()


def _split_node(node_id: str) -> tuple[Path, str]:
    rel, _, func = node_id.partition("::")
    return REPO_ROOT / rel, func


def _function_def(path: Path, func_name: str) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == func_name
        ):
            return node
    return None


def test_expected_seven_physics_invariants_declare_a_falsifier_node() -> None:
    """Every EXTRAPOLATED/SPECULATIVE seven-physics invariant must name a
    node-level falsifier. A missing binding ⇒ no executable falsifier ⇒
    the gate fails closed (this test goes red)."""
    missing = sorted(_EXPECTED_FALSIFIER_INVARIANTS - set(_FALSIFIER_BINDINGS))
    assert not missing, (
        f"seven-physics invariants without a falsifier_test node: {missing}. "
        f"Add 'falsifier_test: <file>::<test_node>' to each in "
        f".claude/physics/INVARIANTS.yaml or the falsifier is non-executable."
    )


@pytest.mark.parametrize(
    ("inv_id", "node_id"),
    sorted(_FALSIFIER_BINDINGS.items()),
    ids=sorted(_FALSIFIER_BINDINGS),
)
def test_falsifier_node_id_is_well_formed(inv_id: str, node_id: str) -> None:
    """``falsifier_test`` must be a ``file::test_func`` pytest node id."""
    assert "::" in node_id, f"{inv_id}: falsifier_test {node_id!r} is not a pytest node id"
    rel, func = node_id.split("::", 1)
    assert rel.endswith(".py"), f"{inv_id}: falsifier file {rel!r} is not a .py module"
    assert func.startswith("test_"), f"{inv_id}: falsifier func {func!r} is not a test_* node"


@pytest.mark.parametrize(
    ("inv_id", "node_id"),
    sorted(_FALSIFIER_BINDINGS.items()),
    ids=sorted(_FALSIFIER_BINDINGS),
)
def test_falsifier_node_resolves_to_a_real_function(inv_id: str, node_id: str) -> None:
    """The named node must AST-resolve to a defined ``test_*`` function in
    an existing file — a *collectable* pytest node, not a dangling string."""
    path, func = _split_node(node_id)
    assert path.is_file(), f"{inv_id}: falsifier file does not exist: {path}"
    fn = _function_def(path, func)
    assert fn is not None, f"{inv_id}: falsifier node {func!r} not defined in {path.name}"


@pytest.mark.parametrize(
    ("inv_id", "node_id"),
    sorted(_FALSIFIER_BINDINGS.items()),
    ids=sorted(_FALSIFIER_BINDINGS),
)
def test_falsifier_node_references_its_invariant(inv_id: str, node_id: str) -> None:
    """The falsifier must be provably *about* the invariant it falsifies, so the
    registry binding cannot silently drift to an unrelated test.

    Accepted provenance, in order of strength:
      (a) the invariant id appears in the falsifier node's own body
          (e.g. an ``assert "INV-..." in reason`` on the violation path), OR
      (b) the invariant id is declared in the falsifier *file's* module
          docstring. Form (b) is required for INV-SIMULATION-FALSIFICATION,
          whose violation verdict cites the per-signature id (by design the
          invariant is an enumerable signature registry, not a single bound),
          so the umbrella id lives at file scope rather than node scope.
    """
    path, func = _split_node(node_id)
    full_src = path.read_text(encoding="utf-8")
    fn = _function_def(path, func)
    assert fn is not None
    body_src = ast.get_source_segment(full_src, fn) or ""
    module_doc = ast.get_docstring(ast.parse(full_src)) or ""
    assert inv_id in body_src or inv_id in module_doc, (
        f"{inv_id}: falsifier node {func!r} does not reference {inv_id} in its body "
        f"nor in the module docstring of {path.name}; the binding may have drifted "
        f"to an unrelated test."
    )


@pytest.mark.parametrize(
    ("inv_id", "node_id"),
    sorted(_FALSIFIER_BINDINGS.items()),
    ids=sorted(_FALSIFIER_BINDINGS),
)
def test_falsifier_node_exercises_a_violation_path(inv_id: str, node_id: str) -> None:
    """The falsifier must drive the bound to its *failing* verdict, not merely
    a passing path. We require the node to assert a False/violation outcome
    (``is_within_budget is False``, ``is_extended_consistent is False``,
    ``is_bound_consistent is False``, or ``hardware_class_ruled_out is True``)
    so a vacuous always-green test cannot pose as a falsifier."""
    path, func = _split_node(node_id)
    fn = _function_def(path, func)
    assert fn is not None
    src = ast.get_source_segment(path.read_text(encoding="utf-8"), fn) or ""
    violation_markers = (
        "is_within_budget is False",
        "is_extended_consistent is False",
        "is_bound_consistent is False",
        "hardware_class_ruled_out is True",
    )
    assert any(marker in src for marker in violation_markers), (
        f"{inv_id}: falsifier node {func!r} does not assert a violation verdict "
        f"(expected one of {violation_markers}); it does not exercise the failing side "
        f"of the bound and is therefore not an executable falsifier."
    )
