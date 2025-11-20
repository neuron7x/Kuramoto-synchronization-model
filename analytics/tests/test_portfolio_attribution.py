from __future__ import annotations

import pandas as pd
import pytest

from analytics.portfolio_attribution import (
    PortfolioAttributionConfig,
    PortfolioAttributionEngine,
)


def _build_sample_inputs() -> dict[str, object]:
    dates = pd.date_range("2023-01-01", periods=30, freq="D")

    strategy_pnl = pd.DataFrame(
        {
            "alpha": [0.8, 1.2, 0.6, 0.9, 1.1, 0.5, 0.7, 1.3, 1.0, 0.4] * 3,
            "beta": [0.4, -0.2, 0.1, 0.3, 0.2, -0.1, 0.0, 0.2, 0.3, 0.1] * 3,
            "gamma": [-0.1, 0.0, 0.1, 0.05, -0.05, 0.0, 0.1, -0.1, 0.0, 0.05] * 3,
        },
        index=dates,
    )

    instrument_pnl = pd.DataFrame(
        {
            "AAPL": [0.3, 0.4, 0.2, 0.3, 0.4, 0.1, 0.2, 0.5, 0.4, 0.1] * 3,
            "MSFT": [0.4, 0.5, 0.3, 0.2, 0.4, 0.3, 0.2, 0.6, 0.5, 0.2] * 3,
            "TSLA": [0.5, 0.3, 0.2, 0.4, 0.5, 0.2, 0.3, 0.4, 0.4, 0.2] * 3,
        },
        index=dates,
    )

    factor_exposures = pd.DataFrame(
        {
            "market": [0.6, 0.55, 0.5, 0.65, 0.6, 0.52, 0.58, 0.62, 0.57, 0.6] * 3,
            "value": [0.25, 0.2, 0.22, 0.24, 0.23, 0.19, 0.21, 0.26, 0.24, 0.22] * 3,
            "momentum": [0.15, 0.18, 0.2, 0.14, 0.17, 0.16, 0.18, 0.12, 0.19, 0.18] * 3,
        },
        index=dates,
    )

    factor_returns = pd.DataFrame(
        {
            "market": [
                0.01,
                -0.005,
                0.008,
                0.012,
                -0.002,
                0.007,
                -0.004,
                0.009,
                0.0,
                0.005,
            ]
            * 3,
            "value": [
                0.004,
                0.003,
                0.002,
                0.001,
                -0.001,
                0.002,
                0.003,
                -0.002,
                0.001,
                0.002,
            ]
            * 3,
            "momentum": [
                0.006,
                -0.004,
                0.005,
                0.007,
                0.003,
                -0.002,
                0.004,
                0.005,
                0.002,
                0.003,
            ]
            * 3,
        },
        index=dates,
    )

    instrument_exposures = pd.DataFrame(
        {
            "AAPL": [15, 16, 15, 15, 16, 15, 15, 16, 16, 15] * 3,
            "MSFT": [18, 17, 18, 19, 18, 17, 18, 19, 18, 18] * 3,
            "TSLA": [20, 19, 21, 20, 21, 19, 20, 21, 20, 20] * 3,
        },
        index=dates,
        dtype=float,
    )

    regimes = pd.Series(
        ["bull", "bear", "neutral"] * 10,
        index=dates,
    )

    return {
        "strategy_pnl": strategy_pnl,
        "instrument_pnl": instrument_pnl,
        "factor_exposures": factor_exposures,
        "factor_returns": factor_returns,
        "instrument_exposures": instrument_exposures,
        "regime_series": regimes,
    }


def test_portfolio_attribution_report_generation() -> None:
    inputs = _build_sample_inputs()
    engine = PortfolioAttributionEngine(
        strategy_pnl=inputs["strategy_pnl"],
        instrument_pnl=inputs["instrument_pnl"],
        factor_exposures=inputs["factor_exposures"],
        factor_returns=inputs["factor_returns"],
        regime_series=inputs["regime_series"],
        hedge_pairs={"alpha_vs_beta": ("alpha", "beta")},
        instrument_exposures=inputs["instrument_exposures"],
        config=PortfolioAttributionConfig(
            concentration_limit=0.55,
            exposure_limit=0.6,
            min_history=20,
        ),
    )

    report = engine.run()

    total_expected = float(inputs["strategy_pnl"].to_numpy().sum())
    assert pytest.approx(total_expected, rel=1e-9) == report.total_pnl

    strategy_totals = inputs["strategy_pnl"].sum()
    strategy_breakdown = {item.name: item for item in report.strategy_breakdown}
    assert set(strategy_breakdown) == set(strategy_totals.index)
    assert (
        pytest.approx(strategy_totals["alpha"], rel=1e-9)
        == strategy_breakdown["alpha"].total_pnl
    )

    factor_contributions = inputs["factor_exposures"] * inputs["factor_returns"]
    factor_totals = factor_contributions.sum()
    factor_breakdown = {item.name: item for item in report.factor_breakdown}
    for factor, value in factor_totals.items():
        assert pytest.approx(value, rel=1e-9) == factor_breakdown[factor].total_pnl

    exposures = inputs["factor_exposures"].abs().mean()
    factor_exposures = {item.name: item for item in report.factor_exposures}
    for factor, value in exposures.items():
        assert pytest.approx(value, rel=1e-9) == factor_exposures[factor].exposure

    assert report.hedge_effectiveness, "hedge effectiveness should be computed"
    hedge = report.hedge_effectiveness[0]
    assert hedge.primary == "alpha"
    assert hedge.hedge == "beta"
    assert 0.0 <= hedge.effectiveness <= 1.0

    assert report.regime_stability, "regime stability metrics expected"
    alpha_metrics = next(
        item for item in report.regime_stability if item.strategy == "alpha"
    )
    assert alpha_metrics.metrics, "per-regime metrics should exist"

    assert report.alerts, "expected concentration alerts based on configured limits"


def test_portfolio_attribution_validation_errors() -> None:
    inputs = _build_sample_inputs()
    bad_returns = inputs["factor_returns"].rename(columns={"market": "mkt"})

    with pytest.raises(ValueError):
        PortfolioAttributionEngine(
            strategy_pnl=inputs["strategy_pnl"],
            instrument_pnl=inputs["instrument_pnl"],
            factor_exposures=inputs["factor_exposures"],
            factor_returns=bad_returns,
            regime_series=inputs["regime_series"],
        )


def test_portfolio_attribution_instrument_exposure_validation() -> None:
    inputs = _build_sample_inputs()
    bad_exposures = inputs["instrument_exposures"].rename(columns={"AAPL": "AAPL_ALT"})

    with pytest.raises(
        ValueError,
        match="instrument_exposures columns must match instrument_pnl columns",
    ):
        PortfolioAttributionEngine(
            strategy_pnl=inputs["strategy_pnl"],
            instrument_pnl=inputs["instrument_pnl"],
            factor_exposures=inputs["factor_exposures"],
            factor_returns=inputs["factor_returns"],
            regime_series=inputs["regime_series"],
            instrument_exposures=bad_exposures,
        )
