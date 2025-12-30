from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from hypothesis import given, settings, strategies as st

from tradepulse.core.neuro.serotonin.certify import (
    run_basal_ganglia_integration,
    run_regime,
)
from tradepulse.core.neuro.serotonin.regimes import build_regimes
from tradepulse.core.neuro.serotonin.serotonin_controller import SerotoninController


DATA_ROOT = Path(__file__).resolve().parents[4] / "data"
DEFAULT_SERIES = pd.read_csv(DATA_ROOT / "sample_crypto_ohlcv.csv")["close"].to_numpy()
DEFAULT_FLIP_WINDOW = 10
DEFAULT_FLIP_LIMIT = 7


def test_build_regimes_deterministic():
    base = DEFAULT_SERIES[:128]
    r1 = build_regimes(base, seed=42)
    r2 = build_regimes(base, seed=42)
    assert set(r1.keys()) == set(r2.keys())
    for key in r1:
        assert np.allclose(r1[key], r2[key])


@given(
    st.lists(
        st.tuples(
            st.floats(min_value=0.0, max_value=3.0),
            st.floats(min_value=-0.6, max_value=0.0),
            st.floats(min_value=0.0, max_value=2.0),
        ),
        min_size=5,
        max_size=25,
    )
)
@settings(max_examples=50, deadline=800)
def test_serotonin_sequence_properties(seq):
    ctrl = SerotoninController()
    holds: list[bool] = []
    levels: list[float] = []

    for stress, drawdown, novelty in seq:
        res = ctrl.step(stress=stress, drawdown=drawdown, novelty=novelty)
        assert 0.0 <= res.level <= 1.0
        assert math.isfinite(res.temperature_floor)
        holds.append(bool(res.hold))
        levels.append(float(res.level))

    ctrl.reset()
    levels_repeat: list[float] = []
    for stress, drawdown, novelty in seq:
        res = ctrl.step(stress=stress, drawdown=drawdown, novelty=novelty)
        levels_repeat.append(float(res.level))

    assert np.allclose(levels, levels_repeat)

    if len(holds) > 1:
        window = holds[-DEFAULT_FLIP_WINDOW:]
        flips = sum(window[i] != window[i - 1] for i in range(1, len(window)))
        assert flips <= DEFAULT_FLIP_LIMIT


def test_regime_harness_smoke(tmp_path: Path):
    prices = np.linspace(100.0, 101.0, num=64, dtype=float)
    ctrl = SerotoninController()
    metrics = run_regime(
        "calm",
        prices,
        controller=ctrl,
        flip_window=DEFAULT_FLIP_WINDOW,
        flip_limit=DEFAULT_FLIP_LIMIT,
    )
    assert metrics.violations == []
    assert 0.0 <= metrics.min_level <= metrics.max_level <= 1.0


def test_basal_ganglia_respects_serotonin_hold():
    violations = run_basal_ganglia_integration(seed=7)
    assert violations == []
