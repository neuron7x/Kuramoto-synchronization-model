# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for the clamp-void predictor / safe re-pinner.

The keystone is ``test_new_clamp_is_a_hard_void``: a clamp with no registry
entry is NEVER auto-fixed (it needs a human-declared reason), while a pure line
shift is classified safe. ``test_real_tree_is_in_sync`` proves the committed
registry matches the tree (the predictor agrees with the gate).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

_ROOT = Path(__file__).resolve().parents[2]


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "predict_clamp_voids", _ROOT / "tools" / "physics" / "predict_clamp_voids.py"
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


_p = _load()


def test_real_tree_is_in_sync() -> None:
    assert _p.main([]) == 0


def test_classify_safe_line_shift() -> None:
    live = {("a.py", "saturate_clip"): {192}}
    pinned = {("a.py", "saturate_clip"): {189}}
    buckets = _p.classify(live, pinned)
    assert buckets["SAFE_LINE_SHIFT"] == [
        {"path": "a.py", "shape": "saturate_clip", "from": [189], "to": [192]}
    ]
    assert buckets["NEW_CLAMP"] == []


def test_new_clamp_is_a_hard_void() -> None:
    """A clamp with no registry entry is NEW_CLAMP — never a safe auto-fix."""
    live = {("b.py", "floor_builtin"): {10}}
    pinned: dict[tuple[str, str], set[int]] = {}
    buckets = _p.classify(live, pinned)
    assert buckets["NEW_CLAMP"] == [{"path": "b.py", "shape": "floor_builtin", "lines": [10]}]
    assert buckets["SAFE_LINE_SHIFT"] == []


def test_count_change_is_not_safe() -> None:
    """Two live clamps where the registry pinned one → not a pure shift."""
    live = {("c.py", "epsilon_add"): {10, 20}}
    pinned = {("c.py", "epsilon_add"): {10}}
    buckets = _p.classify(live, pinned)
    assert buckets["SAFE_LINE_SHIFT"] == []
    assert buckets["NEW_CLAMP"] and buckets["NEW_CLAMP"][0]["added"] == [20]


def test_removed_clamp_detected() -> None:
    live: dict[tuple[str, str], set[int]] = {}
    pinned = {("d.py", "cap_builtin"): {5}}
    buckets = _p.classify(live, pinned)
    assert buckets["REMOVED_CLAMP"] == [{"path": "d.py", "shape": "cap_builtin", "lines": [5]}]


def test_apply_safe_repins_rewrites_only_the_line() -> None:
    text = "  sites:\n  - core/x.py:189\n  - core/y.py:7\n"
    safe = [{"path": "core/x.py", "shape": "s", "from": [189], "to": [192]}]
    out = _p.apply_safe_repins(text, safe)
    assert "core/x.py:192" in out
    assert "core/x.py:189" not in out
    assert "core/y.py:7" in out  # untouched
