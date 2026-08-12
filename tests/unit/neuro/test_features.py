# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import numpy as np

from core.neuro.features import EWEntropy, EWEntropyConfig, ema_update, ewvar_update


def test_ema_update_tracks_recent_values() -> None:
    ema = 0.0
    for value in [0.0, 1.0, 2.0, -1.0]:
        ema = float(ema_update(ema, value, span=4))
    assert 0.0 < ema < 1.0


def test_ewvar_update_matches_numpy_var() -> None:
    rng = np.random.default_rng(0)
    x = rng.normal(0.0, 0.2, 128).astype(np.float32)
    ema = 0.0
    var = 0.0
    for sample in x:
        ema = float(ema_update(ema, float(sample), span=16))
        pe = float(sample) - ema
        var = float(ewvar_update(var, pe, lam=0.9, eps=1e-6))
    ref = float(np.var(x, ddof=0))
    assert 0.5 * ref < var < 1.5 * ref


def test_entropy_updates_within_expected_bounds() -> None:
    cfg = EWEntropyConfig(bins=16, xmin=-1.0, xmax=1.0, decay=0.9)
    ent = EWEntropy(cfg)
    values = np.linspace(-1.0, 1.0, 64)
    outputs = [ent.update(float(v)) for v in values]
    assert all(h >= 0.0 for h in outputs)
    assert outputs[-1] > outputs[0]
    assert ent.value == outputs[-1]


def test_entropy_clamps_to_last_bin() -> None:
    cfg = EWEntropyConfig(bins=8, xmin=-0.5, xmax=0.5, decay=0.5)
    ent = EWEntropy(cfg)
    ent.update(-10.0)
    ent.update(10.0)
    assert ent.value >= 0.0
    assert np.isfinite(ent.value)
