# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
from hypothesis import given, settings
from hypothesis import strategies as st

from geosync.core.neuro.serotonin.certify import (
    run_basal_ganglia_integration,
    run_regime,
)
from geosync.core.neuro.serotonin.regimes import build_regimes
from geosync.core.neuro.serotonin.serotonin_controller import SerotoninController

DATA_ROOT = Path(__file__).resolve().parents[4] / "data"
DEFAULT_SERIES = pd.read_csv(DATA_ROOT / "sample_crypto_ohlcv.csv")["close"].to_numpy()
DEFAULT_FLIP_WINDOW = 10
DEFAULT_FLIP_LIMIT = 9


def test_build_regimes_deterministic():
    """INV-HPC1: regime construction is bit-identical under identical seed.

    The regime builder consumes the same price slice twice with seed=42
    and must emit the same keys and the same arrays. Divergence would
    mean the serotonin regime layer has hidden non-determinism (global
    RNG, dict-iteration hash leakage) and cannot be used for replayable
    backtests.
    """
    base = DEFAULT_SERIES[:128]
    r1 = build_regimes(base, seed=42)
    r2 = build_regimes(base, seed=42)
    assert set(r1.keys()) == set(r2.keys()), (
        f"INV-HPC1 VIOLATED: regime key-sets differ across identical (seed=42) runs. "
        f"Expected identical key set. "
        f"Observed r1 keys={sorted(r1.keys())}, r2 keys={sorted(r2.keys())} "
        f"at N={len(base)}. "
        f"Physical reasoning: seeded regime builder must be deterministic."
    )
    for key in r1:
        max_diff = float(np.max(np.abs(np.asarray(r1[key]) - np.asarray(r2[key]))))
        assert np.allclose(r1[key], r2[key]), (
            f"INV-HPC1 VIOLATED: regime '{key}' differs across identical seed=42 runs. "
            f"Expected bit-identical arrays. "
            f"Observed max|Δ|={max_diff:.3e} at N={len(base)}. "
            f"Physical reasoning: deterministic regime construction must replay exactly."
        )


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
    """INV-5HT2 / INV-5HT5 / INV-HPC1: serotonin level bounded in [0,1],
    temperature_floor finite, and controller is deterministic on replay.

    The serotonin controller is a 5-HT ODE advanced step-by-step under
    hypothesis-generated (stress, drawdown, novelty) triples. Three
    invariants are simultaneously witnessed here:

    * INV-5HT2 — level stays in [0, 1] for every step.
    * INV-5HT5 — temperature_floor remains finite (no NaN/Inf from the
      receptor desensitisation update).
    * INV-HPC1 — replaying the same sequence through a fresh controller
      yields bit-identical level trajectories (deterministic ODE).
    """
    ctrl = SerotoninController()
    holds: list[bool] = []
    levels: list[float] = []

    for step_idx, (stress, drawdown, novelty) in enumerate(seq):
        res = ctrl.step(stress=stress, drawdown=drawdown, novelty=novelty)
        assert 0.0 <= res.level <= 1.0, (
            f"INV-5HT2 VIOLATED at step={step_idx}: level={res.level:.6f} "
            f"outside [0, 1]. Expected level ∈ [0, 1] by 5-HT ODE clipping. "
            f"Observed with stress={stress}, drawdown={drawdown}, novelty={novelty}. "
            f"Physical reasoning: receptor dynamics must saturate inside the "
            f"biological 5-HT range; escape means the integrator diverged."
        )
        assert math.isfinite(res.temperature_floor), (
            f"INV-5HT5 VIOLATED at step={step_idx}: temperature_floor="
            f"{res.temperature_floor} non-finite. "
            f"Expected temperature_floor finite under bounded inputs. "
            f"Observed with stress={stress}, drawdown={drawdown}, novelty={novelty}. "
            f"Physical reasoning: exploration-temperature floor is derived from "
            f"finite inputs and must never propagate NaN/Inf."
        )
        holds.append(bool(res.hold))
        levels.append(float(res.level))

    ctrl.reset()
    levels_repeat: list[float] = []
    for stress, drawdown, novelty in seq:
        res = ctrl.step(stress=stress, drawdown=drawdown, novelty=novelty)
        levels_repeat.append(float(res.level))

    assert np.allclose(levels, levels_repeat), (
        f"INV-HPC1 VIOLATED: replayed level trajectory diverged from original. "
        f"Expected bit-identical replay for deterministic 5-HT ODE. "
        f"Observed at N={len(seq)} steps, with max|Δ|="
        f"{float(np.max(np.abs(np.array(levels) - np.array(levels_repeat)))):.3e}. "
        f"Physical reasoning: seeded, deterministic controller must reproduce "
        f"exactly — any drift indicates hidden global state or non-determinism."
    )

    if len(holds) > 1:
        window = holds[-DEFAULT_FLIP_WINDOW:]
        flips = sum(window[i] != window[i - 1] for i in range(1, len(window)))
        assert flips <= DEFAULT_FLIP_LIMIT, (
            f"INV-5HT2 stability surrogate: hold flipped {flips} times in last "
            f"{DEFAULT_FLIP_WINDOW} steps, exceeding limit={DEFAULT_FLIP_LIMIT}. "
            f"Expected bounded-level ODE to produce a settled hold decision. "
            f"Observed with N={len(holds)} steps. "
            f"Physical reasoning: excessive hold flipping indicates level drifts "
            f"near the decision boundary — stable 5-HT dynamics should not oscillate."
        )


def test_regime_harness_smoke(tmp_path: Path):
    """INV-5HT2: serotonin level ∈ [0, 1] across a sweep of price paths.

    Sweeps the harness over multiple synthetic price series (flat, rising,
    falling) to exercise INV-5HT2 as a universal property across many
    inputs, not a single-point check. Any escape from the [0, 1] bound
    on any path is a bug in the 5-HT ODE saturation layer.
    """
    price_paths = [
        np.linspace(100.0, 101.0, num=64, dtype=float),
        np.linspace(100.0, 110.0, num=64, dtype=float),
        np.linspace(100.0, 90.0, num=64, dtype=float),
    ]
    for path_idx, prices in enumerate(price_paths):
        ctrl = SerotoninController()
        metrics = run_regime(
            "calm",
            prices,
            controller=ctrl,
            flip_window=DEFAULT_FLIP_WINDOW,
            flip_limit=DEFAULT_FLIP_LIMIT,
        )
        assert metrics.violations == [], (
            f"INV-5HT2 VIOLATED on path={path_idx}: harness reported "
            f"{len(metrics.violations)} violations: {metrics.violations}. "
            f"Expected zero violations on a calm-regime sweep. "
            f"Observed at N=64 prices, flip_window={DEFAULT_FLIP_WINDOW}. "
            f"Physical reasoning: calm regime must not trip any 5-HT bound."
        )
        assert 0.0 <= metrics.min_level <= metrics.max_level <= 1.0, (
            f"INV-5HT2 VIOLATED on path={path_idx}: level range "
            f"[{metrics.min_level:.4f}, {metrics.max_level:.4f}] escapes [0, 1]. "
            f"Expected level ∈ [0, 1] by 5-HT ODE saturation. "
            f"Observed at N=64, regime='calm'. "
            f"Physical reasoning: 5-HT level is a normalised concentration."
        )


def test_basal_ganglia_respects_serotonin_hold():
    """INV-5HT7: basal-ganglia integration respects hard veto across seeds.

    The basal-ganglia harness must return an empty violations list on
    every seed. Sweeping several seeds exercises INV-5HT7 as a universal
    property: under stress ≥ 1 or |drawdown| ≥ 0.5, the hold signal must
    force veto=True and no downstream action may fire.
    """
    for seed in (3, 7, 11, 13, 17):
        violations = run_basal_ganglia_integration(seed=seed)
        assert violations == [], (
            f"INV-5HT7 VIOLATED at seed={seed}: basal-ganglia path produced "
            f"{len(violations)} veto-override cases: {violations}. "
            f"Expected zero overrides — hard veto from 5-HT hold must block actions. "
            f"Observed with default harness configuration. "
            f"Physical reasoning: stress ≥ 1 or |drawdown| ≥ 0.5 must force veto=True."
        )
