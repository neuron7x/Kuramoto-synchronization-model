"""T6 · predictive envelope is seeded and reproducible."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

EVAL_SCRIPT = REPO / "scripts" / "evaluate_cross_asset_kuramoto_shadow.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("shadow_eval", EVAL_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_envelope_shape() -> None:
    mod = _load_module()
    oos = mod._demo_oos_log_returns()
    env = mod._build_envelope(
        oos,
        n_paths=mod.ENVELOPE_N_PATHS,
        block_len=mod.ENVELOPE_BLOCK_LEN,
        horizon=mod.ENVELOPE_HORIZON_BARS,
        seed=mod.ENVELOPE_SEED,
    )
    assert set(env.columns) == {"forward_bar", "p05", "p25", "p50", "p75", "p95"}
    assert len(env) == mod.ENVELOPE_HORIZON_BARS
    # Quantile monotonicity at every bar
    for _, row in env.iterrows():
        assert row["p05"] <= row["p25"] <= row["p50"] <= row["p75"] <= row["p95"]


def test_envelope_is_seeded_and_reproducible() -> None:
    mod = _load_module()
    oos = mod._demo_oos_log_returns()
    a = mod._build_envelope(
        oos,
        n_paths=mod.ENVELOPE_N_PATHS,
        block_len=mod.ENVELOPE_BLOCK_LEN,
        horizon=mod.ENVELOPE_HORIZON_BARS,
        seed=mod.ENVELOPE_SEED,
    )
    b = mod._build_envelope(
        oos,
        n_paths=mod.ENVELOPE_N_PATHS,
        block_len=mod.ENVELOPE_BLOCK_LEN,
        horizon=mod.ENVELOPE_HORIZON_BARS,
        seed=mod.ENVELOPE_SEED,
    )
    pd.testing.assert_frame_equal(a, b, check_dtype=False)


def test_envelope_changes_with_seed() -> None:
    mod = _load_module()
    oos = mod._demo_oos_log_returns()
    a = mod._build_envelope(oos, 200, mod.ENVELOPE_BLOCK_LEN, 30, seed=1)
    b = mod._build_envelope(oos, 200, mod.ENVELOPE_BLOCK_LEN, 30, seed=2)
    # At least one quantile at one bar differs (sanity — seed actually seeds)
    assert not a.equals(b)


def test_envelope_position_labels_are_in_vocab() -> None:
    mod = _load_module()
    oos = mod._demo_oos_log_returns()
    env = mod._build_envelope(oos, 100, mod.ENVELOPE_BLOCK_LEN, 30, seed=42)
    vocab = {"below_p05", "p05_p25", "p25_p75", "p75_p95", "above_p95", "out_of_horizon"}
    for cum in (-1.0, 0.0, 1.0):
        label = mod._envelope_position(cum, 5, env)
        assert label in vocab
    assert mod._envelope_position(0.0, 999, env) == "out_of_horizon"
