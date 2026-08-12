# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for the WP-01 context-manifest validator.

Proves the committed example validates and that the gate fails closed on each
drift class: an unknown claim tier (e.g. an inflated 'WORLD_CLASS' label), an
inverted time window, and a missing required field.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
_EXAMPLE = _ROOT / "schemas" / "inference" / "examples" / "context_manifest.example.json"
_SCHEMA = _ROOT / "schemas" / "inference" / "context_manifest.schema.json"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "validate_context_manifest", _ROOT / "tools" / "inference" / "validate_context_manifest.py"
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


_vcm = _load()
_LADDER = _vcm._load_ladder()


def _schema() -> dict[str, Any]:
    return json.loads(_SCHEMA.read_text(encoding="utf-8"))


def _example() -> dict[str, Any]:
    return json.loads(_EXAMPLE.read_text(encoding="utf-8"))


def test_committed_example_is_valid() -> None:
    assert _vcm.validate(_example(), _schema(), _LADDER) == []


def test_claim_tier_must_be_a_ladder_rung() -> None:
    m = _example()
    m["claim_tier"] = "WORLD_CLASS"
    errors = _vcm.validate(m, _schema(), _LADDER)
    assert any("not a rung" in e for e in errors)


def test_inverted_window_fails() -> None:
    m = _example()
    m["time_window"]["end"] = m["time_window"]["start"]
    errors = _vcm.validate(m, _schema(), _LADDER)
    assert any("start must be strictly before end" in e for e in errors)


def test_missing_null_models_fails() -> None:
    m = _example()
    del m["null_models"]
    errors = _vcm.validate(m, _schema(), _LADDER)
    assert any("null_models" in e for e in errors)


def test_empty_universe_fails() -> None:
    m = _example()
    m["asset_universe"] = []
    errors = _vcm.validate(m, _schema(), _LADDER)
    assert errors


def test_main_exit_codes() -> None:
    assert _vcm.main([str(_EXAMPLE)]) == 0
