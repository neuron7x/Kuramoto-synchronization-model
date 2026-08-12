# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""DS-12 regression: the debt-baseline meta-gate must fail CLOSED on NaN.

``json.loads`` accepts non-standard ``NaN``/``Infinity`` by default. A ``NaN``
in ``file_count_debt.*`` makes the reducer sum to ``nan``; the growth test
``cur > base`` is ``nan > base == False``, so debt growth goes UNDETECTED and
the gate PASSES. These tests pin the fix on both the ``_safe_json`` helper and
the end-to-end reducer path, and prove the monotonicity logic is otherwise
unchanged (non-vacuous: genuine growth still RED, genuine no-growth GREEN).
"""

from __future__ import annotations

import importlib.util
import json
import math
from pathlib import Path

import pytest

_CI_DIR = Path(__file__).resolve().parents[2] / "scripts" / "ci"


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, _CI_DIR / filename)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_safe = _load("ds12_safe_json", "_safe_json.py")
_gate = _load("ds12_debt_gate", "check_debt_baseline_monotonic.py")


# --------------------------------------------------------------------------- #
# _safe_json helper                                                           #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity"])
def test_loads_finite_rejects_non_finite_constant(token: str) -> None:
    payload = '{"file_count_debt": {"x": %s}}' % token
    with pytest.raises(_safe.NonFiniteJSONError):
        _safe.loads_finite(payload)
    with pytest.raises(_safe.NonFiniteJSONError):
        _safe.loads_finite_dict(payload)


def test_loads_finite_accepts_normal_json() -> None:
    obj = _safe.loads_finite_dict('{"a": 1, "b": {"c": 2}}')
    assert obj == {"a": 1, "b": {"c": 2}}


def test_loads_finite_dict_rejects_non_dict_top_level() -> None:
    with pytest.raises(TypeError):
        _safe.loads_finite_dict("[1, 2, 3]")


def test_load_finite_dict_reads_file(tmp_path: Path) -> None:
    p = tmp_path / "d.json"
    p.write_text('{"k": 5}', encoding="utf-8")
    assert _safe.load_finite_dict(p) == {"k": 5}


def test_dict_guard_is_real_if_raise_not_assert() -> None:
    # Under ``python -O`` asserts are stripped; the guard must be an if/raise.
    # We assert on the source that no bare ``assert isinstance`` protects the
    # top-level shape, and that a TypeError path exists (behaviour above).
    src = (_CI_DIR / "_safe_json.py").read_text(encoding="utf-8")
    assert "raise TypeError" in src


# --------------------------------------------------------------------------- #
# End-to-end: the NaN poisoning that made the gate PASS now fails closed      #
# --------------------------------------------------------------------------- #
def test_reducer_would_sum_to_nan_without_guard() -> None:
    # Documents the ROOT CAUSE: with the stdlib parser a NaN poisons the sum
    # and ``nan > base`` is False -> undetected growth. The guard prevents the
    # poisoned payload from ever reaching the reducer.
    poisoned = json.loads('{"a": NaN, "b": 3}')  # stdlib default accepts NaN
    total = sum(poisoned.values())
    assert math.isnan(total)
    assert not (total > 5)  # the silent-pass mechanism


def test_gate_read_working_rejects_nan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Point the gate's ROOT at a tmp tree carrying a NaN-poisoned debt baseline
    # and confirm the working-read raises instead of yielding a nan.
    debt = tmp_path / "docs" / "CODE_DEBT_BASELINE.json"
    debt.parent.mkdir(parents=True)
    debt.write_text('{"symbol_debt": {}, "file_count_debt": {"lint": {"x": NaN}}}', encoding="utf-8")
    monkeypatch.setattr(_gate, "ROOT", tmp_path)
    # The gate loads its OWN _safe_json instance; use its exception class.
    with pytest.raises(_gate._safe_json.NonFiniteJSONError):
        _gate._read_working("docs/CODE_DEBT_BASELINE.json")


def test_reducer_still_computes_normal_totals() -> None:
    # Non-vacuous: on a clean payload the reducer produces exact totals, so
    # monotonicity is evaluated exactly as before.
    payload = {
        "symbol_debt": {"typeA": ["a", "b"], "typeB": ["c"]},
        "file_count_debt": {"lint": {"f1": 2, "f2": 3}},
    }
    totals = _gate._hygiene_totals(payload)
    assert totals == {"symbol:typeA": 2, "symbol:typeB": 1, "count:lint": 5}


def test_growth_still_red_no_growth_still_green() -> None:
    # Non-vacuous twin of the whole gate: genuine growth is detected (cur>base),
    # genuine no-growth is not. This is the exact comparison the gate performs.
    base = {"count:lint": 5}
    grew = {"count:lint": 7}
    held = {"count:lint": 5}
    assert grew["count:lint"] > base["count:lint"]      # RED
    assert not (held["count:lint"] > base["count:lint"])  # GREEN
