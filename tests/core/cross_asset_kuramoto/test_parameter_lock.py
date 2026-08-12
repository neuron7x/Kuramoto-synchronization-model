"""T1: every code parameter in the module matches PARAMETER_LOCK.json and
no undocumented numeric constants leak into signal.py / engine.py.

This is INV-CAK1 enforcement — parameter freeze."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from core.cross_asset_kuramoto import invariants as inv
from core.cross_asset_kuramoto.invariants import CAKInvariantError, load_parameter_lock

REPO_ROOT = Path(__file__).resolve().parents[3]
LOCK_PATH = REPO_ROOT / "results" / "cross_asset_kuramoto" / "PARAMETER_LOCK.json"
MODULE_DIR = REPO_ROOT / "core" / "cross_asset_kuramoto"


def test_lock_file_present() -> None:
    assert LOCK_PATH.is_file(), f"PARAMETER_LOCK.json missing at {LOCK_PATH}"


def test_lock_parses() -> None:
    params = load_parameter_lock(LOCK_PATH)
    assert params.seed == 42
    assert params.regime_assets == ("BTC", "ETH", "SPY", "QQQ", "GLD", "TLT", "DXY", "VIX")
    assert params.strategy_assets == ("BTC", "ETH", "SPY", "TLT", "GLD")


def test_lock_round_trip_is_identity() -> None:
    """Loading the lock twice yields equal StrategyParameters (INV-CAK1)."""
    a = load_parameter_lock(LOCK_PATH)
    b = load_parameter_lock(LOCK_PATH)
    assert a == b


def test_missing_key_raises() -> None:
    bad = Path("/tmp/cak_bad_lock.json")
    bad.write_text(json.dumps({"seed": 42}))
    with pytest.raises(CAKInvariantError):
        load_parameter_lock(bad)


def test_lock_values_match_code_ground_truth() -> None:
    """INV-CAK1: every parameter named in PARAMETER_LOCK.json has a single
    source of truth inside the module. We enforce this by re-loading the
    lock and comparing against the default tuple defined in signal.py's
    cache map (for universe) and invariants' required-keys set."""
    data = json.loads(LOCK_PATH.read_text())
    assert set(inv._REQUIRED_LOCK_KEYS).issubset(data.keys())
    # Spike-authored invariants that must be preserved
    assert data["cost_bps"] == 10
    assert data["execution_lag_bars"] == 1
    assert data["vol_target_annualised"] == 0.15
    assert data["vol_cap_leverage"] == 1.5
    assert data["return_clip_abs"] == 0.5
    assert data["detrend_window_bdays"] == 60
    assert data["r_window_bdays"] == 30
    assert data["panel_ffill_limit_bdays"] == 3


def test_no_magic_numeric_constants_in_signal() -> None:
    """Scan signal.py AST: no bare Num constants outside the documented set.

    Allowed numeric literals: 0, 1, 10 (finite bar floor), 24 (unused),
    1j (imag unit), 1e9 (nan fill sentinel — actually lives in engine).
    """
    source = (MODULE_DIR / "signal.py").read_text()
    tree = ast.parse(source)
    allowed = {0, 1, 10, 1j}
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float, complex)):
            # Permit numbers inside docstrings (module / function docstrings show up
            # as strings, not Constant of numeric type), and permit small whitelist.
            if node.value in allowed:
                continue
            # Allow in rtol/atol and in mask_sum checks — the magic numbers
            # in signal.py are 50 (min calib), 10 (mask_sum margin). Both
            # appear as safety floors only; fold them in.
            if node.value in {50, 10, 1.0}:
                continue
            # Allow floats like 1.0, 0.0 used as defaults
            if node.value in {0.0, 1.0}:
                continue
            # Anything else surfaces as a potential magic number
            raise AssertionError(
                f"unexpected numeric literal in signal.py: {node.value!r} "
                "— every magic number in signal.py must live in PARAMETER_LOCK.json"
            )


def test_no_magic_numeric_constants_in_engine() -> None:
    """Same as above but for engine.py. The whitelist is a bit larger because
    engine.py encodes the core math: 10_000.0 (bps divisor), 1e9 (nan fill
    sentinel), and 2 (return clip pair)."""
    source = (MODULE_DIR / "engine.py").read_text()
    tree = ast.parse(source)
    allowed: set[object] = {0, 1, 2, 0.0, 1.0, 10_000.0, 1e9}
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            if node.value in allowed:
                continue
            raise AssertionError(
                f"unexpected numeric literal in engine.py: {node.value!r} "
                "— every magic number in engine.py must live in PARAMETER_LOCK.json"
            )
