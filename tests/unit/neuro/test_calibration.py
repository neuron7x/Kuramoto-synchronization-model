from __future__ import annotations

import warnings

import numpy as np

from core.neuro.amm import AMMConfig
from core.neuro.calibration import CalibConfig, CalibResult, calibrate_random


def test_calibrate_random_respects_bounds() -> None:
    cfg = CalibConfig(
        iters=5,
        seed=0,
        ema_span=(12, 12),
        vol_lambda=(0.9, 0.9),
        alpha=(0.5, 0.5),
        beta=(0.8, 0.8),
        lambda_sync=(0.4, 0.4),
        eta_ricci=(0.3, 0.3),
        rho=(0.02, 0.02),
    )
    rng = np.random.default_rng(42)
    x = rng.normal(0.0, 0.01, 64).astype(np.float32)
    R = rng.uniform(0.2, 0.8, 64).astype(np.float32)
    kappa = rng.normal(0.0, 0.2, 64).astype(np.float32)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        best = calibrate_random(x, R, kappa, cfg)
    assert isinstance(best, AMMConfig)
    assert best.ema_span == 12
    assert best.vol_lambda == 0.9
    assert best.alpha == 0.5
    assert best.beta == 0.8
    assert best.lambda_sync == 0.4
    assert best.eta_ricci == 0.3
    assert best.rho == 0.02


def test_calibrate_random_returns_default_when_no_trials() -> None:
    cfg = CalibConfig(iters=0, seed=1)
    x = np.zeros(16, dtype=np.float32)
    R = np.zeros(16, dtype=np.float32)
    kappa = np.zeros(16, dtype=np.float32)

    best = calibrate_random(x, R, kappa, cfg)
    assert isinstance(best, AMMConfig)
    assert best == AMMConfig()


def test_calibrate_random_can_return_details() -> None:
    cfg = CalibConfig(iters=5, seed=4)
    rng = np.random.default_rng(1)
    x = rng.normal(0.0, 0.01, 32).astype(np.float32)
    R = rng.uniform(0.2, 0.8, 32).astype(np.float32)
    kappa = rng.normal(0.0, 0.2, 32).astype(np.float32)

    result = calibrate_random(x, R, kappa, cfg, return_details=True)

    assert isinstance(result, CalibResult)
    assert isinstance(result.config, AMMConfig)
    assert isinstance(result.score, float)
    assert result.metrics
    assert "corr" in result.metrics
    assert "mean_precision" in result.metrics
    if np.isfinite(result.score):
        assert np.isclose(
            result.score,
            result.metrics["corr"] * result.metrics["mean_precision"],
            rtol=1e-6,
        )
