# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Every gate script must be loadable standalone — path-run, from any cwd.

The 2026-07 assessment found gates that crash with ModuleNotFoundError when
invoked as ``python scripts/...py`` (they assumed ``python -m`` from the repo
root). A gate that cannot start is a gate that silently never gates. This
test loads every ``check_*`` script exactly the way a path-run does (file
location import, no repo root pre-inserted) and fails on any import-time
crash. It is an execution floor for all gates, including the ones that have
no dedicated behavior test yet.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
GATES = sorted(
    [*REPO.glob("scripts/ci/check_*.py"), *REPO.glob("scripts/check_*.py")],
    key=lambda p: p.as_posix(),
)


@pytest.mark.parametrize("gate", GATES, ids=lambda p: p.relative_to(REPO).as_posix())
def test_gate_imports_standalone(gate: Path) -> None:
    saved_path = list(sys.path)
    saved_modules = set(sys.modules)
    # simulate a path-run from a foreign cwd: only the script's own directory,
    # as CPython does for `python <path>`; the gate must bootstrap the rest.
    try:
        sys.path = [str(gate.parent), *[p for p in saved_path if p != str(REPO)]]
        name = f"_gate_smoke_{gate.stem}"
        spec = importlib.util.spec_from_file_location(name, gate)
        assert spec and spec.loader, f"unloadable spec for {gate}"
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)  # main() is guarded by __main__ in every gate
    finally:
        sys.path = saved_path
        # C-extension packages (numpy et al.) corrupt on partial sys.modules
        # eviction and re-import: popping a submodule leaves the next importer
        # with a half-initialised package. Never evict them — they are process
        # singletons, not per-gate state, so keeping them cannot mask a gate's
        # own missing import.
        _protected = ("numpy", "scipy", "pandas", "matplotlib", "pyarrow")
        for extra in set(sys.modules) - saved_modules:
            if extra.split(".", 1)[0] in _protected:
                continue
            sys.modules.pop(extra, None)
