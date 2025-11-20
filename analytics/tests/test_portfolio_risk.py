from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from analytics.portfolio_risk import (
    PortfolioStressTester,
    RiskLimitBreach,
    StressScenario,
    VolatilityScenario,
)


def _build_returns_frame(rows: int = 260) -> pd.DataFrame:
    index = pd.date_range("2023-01-01", periods=rows, freq="D")
    angles = np.linspace(0.0, 12.0, num=rows)
    asset_a = 0.01 * np.sin(angles)
    asset_b = 0.012 * np.cos(angles)
    asset_c = 0.008 * np.sin(angles * 1.5)
    return pd.DataFrame(
        {"AssetA": asset_a, "AssetB": asset_b, "AssetC": asset_c}, index=index
    )


def test_stress_tester_generates_comprehensive_report() -> None:
    returns = _build_returns_frame()
    exposures = {"AssetA": 2_000_000.0, "AssetB": -1_500_000.0, "AssetC": 1_250_000.0}
    tester = PortfolioStressTester(
        returns,
        exposures,
        portfolio_value=5_500_000.0,
        min_history=200,
    )

    shock = StressScenario(
        name="Covid-19 FX Shock",
        shocks={"AssetA": -0.05, "AssetB": -0.07, "AssetC": -0.04},
        description="March 2020 global deleveraging",
        reference_date=datetime(2020, 3, 12, tzinfo=timezone.utc),
    )

    volatility = VolatilityScenario(
        name="Volatility +150%",
        volatility_multiplier=1.5,
        horizon_days=5,
        description="Forward-looking implied vol surge",
    )

    report = tester.run(
        confidence_level=0.99,
        horizon_days=5,
        var_limit=10_000.0,
        expected_shortfall_limit=15_000.0,
        historical_shocks=[shock],
        volatility_scenarios=[volatility],
    )

    assert report.risk_metrics.var > 0.0
    assert report.risk_metrics.expected_shortfall >= report.risk_metrics.var
    assert report.scenario_results[0].name == "Covid-19 FX Shock"
    assert pytest.approx(report.scenario_results[0].pnl, rel=1e-6) == (
        exposures["AssetA"] * -0.05
        + exposures["AssetB"] * -0.07
        + exposures["AssetC"] * -0.04
    )

    vol_result = report.volatility_results[0]
    assert vol_result.name == "Volatility +150%"
    assert pytest.approx(vol_result.projected_var) == pytest.approx(
        vol_result.baseline_var * volatility.volatility_multiplier
    )

    assert any(
        isinstance(breach, RiskLimitBreach) and breach.metric == "var"
        for breach in report.limit_breaches
    )

    markdown = report.to_markdown()
    assert "Portfolio Stress Test Report" in markdown
    assert "Covid-19 FX Shock" in markdown
    assert "Volatility +150%" in markdown


def test_stress_tester_rejects_insufficient_history() -> None:
    returns = _build_returns_frame(rows=50)
    exposures = {"AssetA": 1_000_000.0}
    with pytest.raises(ValueError, match="insufficient history"):
        PortfolioStressTester(
            returns, exposures, portfolio_value=1_500_000.0, min_history=60
        )


def test_volatility_scenario_requires_positive_multiplier() -> None:
    with pytest.raises(ValueError):
        VolatilityScenario(name="invalid", volatility_multiplier=0.0)


def test_stress_scenario_validation() -> None:
    with pytest.raises(ValueError):
        StressScenario(name="", shocks={"AssetA": -0.1})
    with pytest.raises(ValueError):
        StressScenario(name="Test", shocks={})


def test_historical_shocks_require_positive_portfolio_value() -> None:
    returns = _build_returns_frame()
    exposures = {"AssetA": 500_000.0}
    tester = PortfolioStressTester(
        returns,
        exposures,
        portfolio_value=1_000_000.0,
        min_history=100,
    )

    scenario = StressScenario(name="Shock", shocks={"AssetA": -0.05})

    with pytest.raises(ValueError, match="portfolio_value must be positive"):
        tester.evaluate_historical_shocks([scenario], portfolio_value=0.0)

    with pytest.raises(ValueError, match="portfolio_value must be positive"):
        tester.evaluate_historical_shocks([scenario], portfolio_value=-10.0)
