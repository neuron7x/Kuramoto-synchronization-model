from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[3]


def _ensure_yfinance_stub() -> None:
    if "yfinance" in sys.modules:
        return
    module = types.ModuleType("yfinance")

    def _download(*_args: object, **_kwargs: object) -> pd.DataFrame:
        raise AssertionError("tests must monkeypatch yfinance.download; live network is forbidden")

    setattr(module, "download", _download)
    sys.modules["yfinance"] = module


def _ensure_matplotlib_stub() -> None:
    if "matplotlib" in sys.modules:
        return
    matplotlib_module = types.ModuleType("matplotlib")
    pyplot_module = types.ModuleType("matplotlib.pyplot")

    def _forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("contract tests must not touch plotting paths")

    setattr(matplotlib_module, "use", lambda *_args, **_kwargs: None)
    setattr(matplotlib_module, "pyplot", pyplot_module)
    for name in ("subplots", "tight_layout", "close", "savefig", "figure"):
        setattr(pyplot_module, name, _forbidden)
    sys.modules["matplotlib"] = matplotlib_module
    sys.modules["matplotlib.pyplot"] = pyplot_module


def _load_module(module_name: str, relative_path: str):
    _ensure_yfinance_stub()
    _ensure_matplotlib_stub()
    spec = importlib.util.spec_from_file_location(module_name, ROOT / relative_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


wf = _load_module("walk_forward_contracts_under_test", "backtest/walk_forward.py")
eq = _load_module("equity_curve_contracts_under_test", "backtest/geosync_equity_curve.py")


def _market_frame(ticker: str, close: np.ndarray) -> pd.DataFrame:
    index = pd.date_range("2025-01-01", periods=len(close), freq="D")
    columns = pd.MultiIndex.from_tuples([("Close", ticker)])
    return pd.DataFrame(close.reshape(-1, 1), index=index, columns=columns)


def _install_walk_forward_fixture(
    monkeypatch: pytest.MonkeyPatch,
    *,
    cost_bps: float,
) -> dict[str, np.ndarray]:
    ticker = "WF"
    close = np.array([100.0, 101.0, 102.0, 101.5, 103.0, 104.0, 103.0, 105.0, 106.0])
    observed: dict[str, np.ndarray] = {}

    monkeypatch.setattr(wf, "SIGNAL_WINDOW", 2)
    monkeypatch.setattr(wf, "TRAIN_WINDOW", 3)
    monkeypatch.setattr(wf, "TEST_WINDOW", 3)
    monkeypatch.setattr(wf, "MAX_POSITION", 0.25)
    monkeypatch.setattr(wf, "COST_BPS", cost_bps)
    monkeypatch.setattr(wf, "MONTE_CARLO_N", 16)
    monkeypatch.setattr(wf.yf, "download", lambda *_args, **_kwargs: _market_frame(ticker, close))

    def fake_compute_signals(close_input: np.ndarray):
        n = len(close_input)
        gamma = np.full(n, np.nan)
        r = np.zeros(n, dtype=np.float64)
        risk = np.zeros(n, dtype=np.float64)
        momentum = np.zeros(n, dtype=np.float64)
        regimes = ["UNKNOWN"] * n

        r[4], risk[4], momentum[4], regimes[4] = 0.9, 0.8, 0.1, "COHERENT"
        r[5], risk[5], momentum[5], regimes[5] = 0.1, 0.9, -0.1, "DECOHERENT"
        r[6], risk[6], momentum[6], regimes[6] = np.nan, np.nan, np.nan, "COHERENT"
        return gamma, r, risk, momentum, regimes

    def fake_calibrate_thresholds(
        returns: np.ndarray,
        r_series: np.ndarray,
        risk_series: np.ndarray,
        mom_series: np.ndarray,
        regimes: list[str],
    ) -> dict[str, float]:
        observed["returns"] = returns.copy()
        observed["r_series"] = r_series.copy()
        observed["risk_series"] = risk_series.copy()
        observed["mom_series"] = mom_series.copy()
        observed["regimes"] = np.asarray(regimes, dtype=object)
        return {"r_thr": 0.7, "risk_thr": 0.6}

    monkeypatch.setattr(wf, "compute_signals", fake_compute_signals)
    monkeypatch.setattr(wf, "calibrate_thresholds", fake_calibrate_thresholds)
    observed["close"] = close
    return observed


def test_classify_regime_pins_all_public_regime_contracts() -> None:
    assert eq.classify_regime(gamma=1.0, r_val=0.71) == "COHERENT"
    assert eq.classify_regime(gamma=0.55, r_val=0.60) == "METASTABLE"
    assert eq.classify_regime(gamma=2.0, r_val=0.90) == "CRITICAL"
    assert eq.classify_regime(gamma=2.0, r_val=0.20) == "DECOHERENT"


def test_classify_regime_thresholds_are_strict_not_accidentally_inclusive() -> None:
    assert eq.classify_regime(gamma=1.4, r_val=0.70) != "COHERENT"
    assert eq.classify_regime(gamma=1.6, r_val=0.50) == "DECOHERENT"
    assert eq.classify_regime(gamma=1.7, r_val=0.85) == "DECOHERENT"


def test_kuramoto_order_parameter_is_deterministic_finite_and_bounded() -> None:
    prices = np.linspace(100.0, 130.0, 256, dtype=np.float64)

    r_first = eq.compute_kuramoto_r(prices, [2, 5, 10, 20])
    r_second = eq.compute_kuramoto_r(prices, [2, 5, 10, 20])

    assert r_first.shape == prices.shape
    assert np.all(np.isfinite(r_first))
    assert np.all((0.0 <= r_first) & (r_first <= 1.0 + 1e-12))
    np.testing.assert_allclose(r_first, r_second, rtol=0.0, atol=0.0)


def test_walk_forward_kuramoto_handles_zero_and_negative_prices_safely() -> None:
    prices = np.array([100.0, 0.0, -5.0, 101.0, 102.0, 0.0, 103.0, 104.0, 105.0])

    r = wf.compute_kuramoto_r(prices)

    assert r.shape == prices.shape
    assert np.all(np.isfinite(r))
    assert np.all((0.0 <= r) & (r <= 1.0 + 1e-12))


def test_walk_forward_threshold_calibration_is_grid_bound_and_deterministic() -> None:
    returns = np.array([0.0, 0.01, 0.02, -0.005, 0.015, 0.01, -0.002, 0.012])
    r_series = np.full_like(returns, 0.8)
    risk_series = np.full_like(returns, 0.75)
    momentum = np.full_like(returns, 0.05)
    regimes = ["COHERENT"] * len(returns)

    first = wf.calibrate_thresholds(returns, r_series, risk_series, momentum, regimes)
    second = wf.calibrate_thresholds(returns, r_series, risk_series, momentum, regimes)

    assert first == second
    assert first["r_thr"] in {0.5, 0.6, 0.7, 0.8}
    assert first["risk_thr"] in {0.4, 0.5, 0.6, 0.7}


def test_walk_forward_calibration_fails_closed_on_nonfinite_signal_inputs() -> None:
    returns = np.array([0.0, 0.01, -0.01, 0.02, -0.02], dtype=np.float64)
    nan_signal = np.full_like(returns, np.nan)
    regimes = ["COHERENT"] * len(returns)

    params = wf.calibrate_thresholds(returns, nan_signal, nan_signal, nan_signal, regimes)

    assert params == {"r_thr": 0.5, "risk_thr": 0.4}


def test_walk_forward_metrics_are_finite_on_flat_no_trade_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(wf, "MONTE_CARLO_N", 32)
    n = wf.SIGNAL_WINDOW + 60
    zeros = np.zeros(n, dtype=np.float64)

    metrics = wf.compute_metrics(
        strategy_ret=zeros,
        daily_ret=zeros,
        positions=zeros,
        oos_ret=zeros[wf.SIGNAL_WINDOW :],
    )

    assert metrics.total_return == 0.0
    assert metrics.benchmark_return == 0.0
    assert metrics.sharpe == 0.0
    assert metrics.max_drawdown == 0.0
    assert metrics.n_trades == 0
    assert metrics.exposure_pct == 0.0


def test_walk_forward_metrics_detect_trade_transitions_and_drawdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(wf, "MONTE_CARLO_N", 32)
    n = wf.SIGNAL_WINDOW + 80
    strategy_ret = np.zeros(n, dtype=np.float64)
    daily_ret = np.zeros(n, dtype=np.float64)
    positions = np.zeros(n, dtype=np.float64)

    positions[wf.SIGNAL_WINDOW + 5 : wf.SIGNAL_WINDOW + 20] = 0.25
    strategy_ret[wf.SIGNAL_WINDOW + 10] = -0.05
    strategy_ret[wf.SIGNAL_WINDOW + 15] = 0.02
    oos_ret = strategy_ret[wf.SIGNAL_WINDOW :]

    metrics = wf.compute_metrics(strategy_ret, daily_ret, positions, oos_ret)

    assert metrics.n_trades == 2
    assert metrics.max_drawdown < 0.0
    assert metrics.exposure_pct > 0.0
    assert np.isfinite(metrics.total_return)


def test_monte_carlo_sharpe_interval_is_seeded_and_ordered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(wf, "MONTE_CARLO_N", 64)
    oos = np.tile(np.array([0.01, -0.004, 0.002, 0.006, -0.003]), 8)

    first = wf._monte_carlo_sharpe(oos)
    second = wf._monte_carlo_sharpe(oos)

    assert first == second
    assert first[0] <= first[1]
    assert np.all(np.isfinite(first))


def test_run_walk_forward_uses_train_window_and_previous_bar_signals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed = _install_walk_forward_fixture(monkeypatch, cost_bps=0.0)

    result = wf.run_walk_forward("WF")

    assert result is not None
    assert result.train_params == [{"r_thr": 0.7, "risk_thr": 0.6}]
    assert result.positions[5] == pytest.approx(0.25)
    assert result.positions[6] == pytest.approx(-0.1)
    assert result.positions[7] == 0.0
    assert result.oos_returns.shape == (3,)

    close = observed["close"]
    daily_ret = np.zeros(len(close))
    daily_ret[1:] = np.diff(close) / close[:-1]
    np.testing.assert_allclose(observed["returns"], daily_ret[2:5])
    np.testing.assert_allclose(observed["r_series"], np.array([0.0, 0.0, 0.9]))
    np.testing.assert_array_equal(observed["regimes"], np.array(["UNKNOWN", "UNKNOWN", "COHERENT"]))


def test_run_walk_forward_transaction_costs_are_monotone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_walk_forward_fixture(monkeypatch, cost_bps=0.0)
    zero_cost = wf.run_walk_forward("WF")
    _install_walk_forward_fixture(monkeypatch, cost_bps=100.0)
    high_cost = wf.run_walk_forward("WF")

    assert zero_cost is not None
    assert high_cost is not None
    assert high_cost.equity[-1] < zero_cost.equity[-1]


def test_equity_curve_empty_download_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(eq.yf, "download", lambda *_args, **_kwargs: pd.DataFrame())

    assert eq.run_backtest("EMPTY") is None


def test_equity_curve_uses_prior_bar_signal_and_holds_through_metastable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ticker = "TEST"
    close = np.array([100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0])

    monkeypatch.setattr(eq, "WINDOW", 3)
    monkeypatch.setattr(eq, "R_THRESHOLD", 0.7)
    monkeypatch.setattr(eq, "RISK_THRESHOLD", 0.6)
    monkeypatch.setattr(eq.yf, "download", lambda *_args, **_kwargs: _market_frame(ticker, close))
    monkeypatch.setattr(
        eq,
        "compute_kuramoto_r",
        lambda _prices, _timeframes: np.array([0.0, 0.0, 0.0, 0.8, 0.6, 0.2, 0.2, 0.2]),
    )

    class FixedGammaEstimator:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def compute(self, _series: np.ndarray) -> SimpleNamespace:
            return SimpleNamespace(value=1.0, is_valid=True)

    monkeypatch.setattr(eq, "PSDGammaEstimator", FixedGammaEstimator)

    result = eq.run_backtest(ticker)

    assert result is not None
    assert result.positions[3] == 0.0
    np.testing.assert_array_equal(result.positions[4:6], np.array([1.0, 1.0]))
    np.testing.assert_array_equal(result.positions[6:], np.array([0.0, 0.0]))
    assert result.n_trades == 1
    assert result.exposure_pct == pytest.approx(40.0)
    assert result.total_return > 0.0
