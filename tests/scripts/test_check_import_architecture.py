# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Import-architecture ratchet — behavioural tests.

The ratchet's promise is that the canonical-geosync debt set can only
shrink. These tests pin: (1) the live tree holds against its baseline,
(2) a new `src.*` importer is detected as fresh debt, (3) a baseline
entry that no longer violates is flagged as a stale ledger, (4) the
detection regexes match the real violation shapes.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "ci" / "check_import_architecture.py"


def _load() -> Any:
    spec = importlib.util.spec_from_file_location("check_import_architecture", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_import_architecture"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def mod() -> Any:
    return _load()


def test_live_tree_holds_against_baseline(mod: Any) -> None:
    assert mod.main([]) == 0


def test_regexes_match_real_shapes(mod: Any) -> None:
    assert mod._SRC_IMPORT_RE.search("from src.data import x")
    assert mod._SRC_IMPORT_RE.search("import src.geosync.core")
    assert not mod._SRC_IMPORT_RE.search("from geosync.core import x")
    assert mod._PATH_HACK_RE.search("sys.path.insert(0, '..')")
    assert not mod._PATH_HACK_RE.search("p = sys.path")


def test_new_violator_fails(mod: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    base_src, base_hacks = mod._load_baseline()
    monkeypatch.setattr(
        mod, "_scan", lambda: (base_src | {"geosync/brand_new_violator.py"}, base_hacks)
    )
    assert mod.main([]) == 1


def test_stale_baseline_fails(mod: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    base_src, base_hacks = mod._load_baseline()
    # current tree fixed one file that is still in the baseline -> stale ledger
    shrunk = set(sorted(base_src)[1:]) if base_src else set()
    if not base_src:
        pytest.skip("baseline already empty")
    monkeypatch.setattr(mod, "_scan", lambda: (shrunk, base_hacks))
    assert mod.main([]) == 1


def test_write_roundtrips(mod: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bl = tmp_path / "baseline.json"
    monkeypatch.setattr(mod, "BASELINE_PATH", bl)
    monkeypatch.setattr(mod, "_scan", lambda: ({"a/x.py"}, {"b/y.py"}))
    assert mod.main(["--write"]) == 0
    payload = json.loads(bl.read_text(encoding="utf-8"))
    assert payload["src_imports"] == ["a/x.py"]
    assert payload["path_hacks"] == ["b/y.py"]
    assert mod.main([]) == 0  # now current == baseline
