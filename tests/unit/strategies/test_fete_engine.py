"""Unit tests for the FETE integration."""

from __future__ import annotations

import numpy as np

from core.strategies import FETE, FETEConfig, FractalEMA, SigmaController, binary_entropy


def test_binary_entropy_midpoint() -> None:
    result = float(binary_entropy(0.5))
    assert np.isclose(result, np.log(2.0), atol=1e-6)


def test_fractal_ema_update_shape() -> None:
    ema = FractalEMA(shape=(1,), levels=4, base=0.6)
    first = ema.update([1.0])
    second = ema.update([1.0])
    assert second.shape == first.shape


def test_sigma_controller_keeps_tau_in_bounds() -> None:
    controller = SigmaController(entropy_target=0.6, tau_lr=0.02, window=200)
    rng = np.random.default_rng(7)
    for _ in range(200):
        prob = float(np.clip(rng.random(), 1e-3, 1 - 1e-3))
        outcome = int(rng.random() < prob)
        controller.update(prob, outcome)
        controller.update_tau()
    audit = controller.audit()
    assert 0.5 <= controller.tau <= 2.0
    assert {"brier", "ece", "entropy", "tau", "n_obs", "calibrated"} <= set(audit)


def test_fete_backtest_output_shapes() -> None:
    rng = np.random.default_rng(0)
    n = 400
    log_returns = rng.normal(0.0005, 0.015, size=n)
    prices = np.cumprod(1.0 + log_returns)
    probs = 0.5 + 0.15 * np.sin(np.arange(prices.size) / 50.0) + rng.normal(0, 0.08, size=prices.size)
    engine = FETE(FETEConfig())
    result = engine.backtest(prices, probs)
    assert "equity" in result and result["equity"].shape[0] == prices.size - 1
    assert "audit" in result and "brier" in result["audit"]


def test_backtest_resets_state_when_requested() -> None:
    rng = np.random.default_rng(123)
    prices = np.cumprod(1.0 + rng.normal(0.0, 0.01, size=64))
    probs = rng.uniform(0.3, 0.7, size=prices.size)
    engine = FETE()

    engine.backtest(prices, probs)
    history_after_first = len(engine.price_history)
    assert history_after_first == prices.size - 1

    engine.backtest(prices, probs)
    history_after_second = len(engine.price_history)
    assert history_after_second == prices.size - 1


def test_backtest_allows_stateful_runs_when_requested() -> None:
    rng = np.random.default_rng(321)
    prices = np.cumprod(1.0 + rng.normal(0.0, 0.01, size=32))
    probs = rng.uniform(0.4, 0.6, size=prices.size)
    engine = FETE()

    engine.backtest(prices, probs, reset_state=True)
    engine.backtest(prices, probs, reset_state=False)

    # When ``reset_state=False`` we expect the internal histories to accumulate.
    assert len(engine.price_history) == 2 * (prices.size - 1)
