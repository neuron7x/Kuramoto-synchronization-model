# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Determinism + injection tests for spikes/bekenstein_margin_scan.py.

Covers self-audit inference flaws #2 (assert_no_violation never fires) and
#3 (efficiency_margin misnomer → bekenstein_saturation_ratio).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SPIKES_DIR = _REPO_ROOT / "spikes"
if str(_SPIKES_DIR) not in sys.path:
    sys.path.insert(0, str(_SPIKES_DIR))

from bekenstein_margin_scan import (  # noqa: E402
    MarginRow,
    PhysicsViolation,
    assert_no_violation,
    render_markdown,
    rows_to_json,
    scan,
)


def _make_row(ratio: float, name: str = "synthetic") -> MarginRow:
    return MarginRow(
        name=name,
        radius_m=1.0,
        energy_J=1.0,
        theoretical_max_bits=1.0,
        estimated_actual_bits=ratio,
        bekenstein_saturation_ratio=ratio,
        log10_margin=0.0,
    )


def test_scan_is_deterministic() -> None:
    """scan() must return identical tuples across invocations (no RNG, no clock)."""
    a = scan()
    b = scan()
    assert a == b


def test_assert_no_violation_passes_for_canonical_systems() -> None:
    """Real 5-system scan must not raise — all ratios are << 1."""
    rows = scan()
    assert_no_violation(rows)


def test_assert_no_violation_raises_at_margin_one() -> None:
    """Boundary case: ratio == 1.0 must trip the guard (>=, not >)."""
    rows = (_make_row(1.0, name="boundary"),)
    with pytest.raises(PhysicsViolation, match="INV-BEKENSTEIN-COGNITIVE"):
        assert_no_violation(rows)


def test_assert_no_violation_raises_at_margin_above_one() -> None:
    """Strict overrun: ratio = 2.5 must raise."""
    rows = (_make_row(2.5, name="overrun"),)
    with pytest.raises(PhysicsViolation, match="overrun"):
        assert_no_violation(rows)


def test_assert_no_violation_does_not_raise_at_margin_below_one() -> None:
    """Just-below boundary: ratio = 0.999 must pass."""
    rows = (_make_row(0.999, name="subcritical"),)
    assert_no_violation(rows)


def test_render_markdown_uses_renamed_column() -> None:
    """Markdown header must say 'saturation', not 'efficiency'."""
    rows = scan()
    md = render_markdown(rows)
    header = md.splitlines()[0]
    assert "saturation" in header.lower()
    assert "efficiency" not in header.lower()


def test_rows_to_json_uses_new_key() -> None:
    """Serialised dicts must carry bekenstein_saturation_ratio, not efficiency_margin."""
    rows = scan()
    payload = rows_to_json(rows)
    assert payload, "scan returned no rows"
    for entry in payload:
        assert "bekenstein_saturation_ratio" in entry
        assert "efficiency_margin" not in entry


def test_persisted_json_uses_new_key() -> None:
    """The committed bekenstein_scan_results.json must reflect the renamed key."""
    json_path = _REPO_ROOT / "spikes" / "bekenstein_scan_results.json"
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert isinstance(data, list) and data
    for entry in data:
        assert "bekenstein_saturation_ratio" in entry
        assert "efficiency_margin" not in entry
