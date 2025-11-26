"""Tests for performance budget loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from .budget_loader import BudgetLoader
from .multi_exchange_replay import PerformanceBudget


@pytest.fixture
def budget_loader() -> BudgetLoader:
    """Create budget loader instance."""
    return BudgetLoader()


def test_load_default_budget(budget_loader: BudgetLoader) -> None:
    """Test loading default budget."""
    budget = budget_loader.get_default_budget()

    assert isinstance(budget, PerformanceBudget)
    assert budget.latency_median_ms > 0
    assert budget.latency_p95_ms > budget.latency_median_ms
    assert budget.throughput_min_tps > 0


def test_load_exchange_budget(budget_loader: BudgetLoader) -> None:
    """Test loading exchange-specific budget."""
    coinbase_budget = budget_loader.get_exchange_budget("coinbase")
    binance_budget = budget_loader.get_exchange_budget("binance")
    default_budget = budget_loader.get_default_budget()

    # Coinbase should have different thresholds than default
    assert coinbase_budget.latency_median_ms != default_budget.latency_median_ms

    # Binance should have tighter latency requirements than Coinbase
    assert binance_budget.latency_median_ms < coinbase_budget.latency_median_ms


def test_load_scenario_budget(budget_loader: BudgetLoader) -> None:
    """Test loading scenario-specific budget."""
    flash_crash_budget = budget_loader.get_scenario_budget("flash_crash")
    stable_budget = budget_loader.get_scenario_budget("stable_market")

    # Flash crash should allow higher latency and slippage
    assert flash_crash_budget.latency_median_ms > stable_budget.latency_median_ms
    assert flash_crash_budget.slippage_median_bps > stable_budget.slippage_median_bps


def test_load_environment_budget(budget_loader: BudgetLoader) -> None:
    """Test loading environment-specific budget."""
    prod_budget = budget_loader.get_environment_budget("production")
    staging_budget = budget_loader.get_environment_budget("staging")
    dev_budget = budget_loader.get_environment_budget("development")

    # Production should have strictest requirements
    assert prod_budget.latency_median_ms < staging_budget.latency_median_ms
    assert staging_budget.latency_median_ms < dev_budget.latency_median_ms

    # Production should require highest throughput
    assert prod_budget.throughput_min_tps > staging_budget.throughput_min_tps


def test_load_component_budget(budget_loader: BudgetLoader) -> None:
    """Test loading component-specific budget."""
    ingestion_budget = budget_loader.get_component_budget("ingestion")
    execution_budget = budget_loader.get_component_budget("execution")

    # Execution should have tighter latency requirements
    assert execution_budget.latency_median_ms < ingestion_budget.latency_median_ms

    # Execution should require higher throughput
    assert execution_budget.throughput_min_tps > ingestion_budget.throughput_min_tps


def test_budget_priority(budget_loader: BudgetLoader) -> None:
    """Test budget priority selection."""
    # Scenario should take priority over exchange
    scenario_budget = budget_loader.get_budget(
        exchange="coinbase", scenario="flash_crash"
    )
    flash_crash_only = budget_loader.get_scenario_budget("flash_crash")

    # Should match scenario budget, not exchange
    assert scenario_budget.latency_median_ms == flash_crash_only.latency_median_ms

    # Exchange should take priority over environment
    exchange_budget = budget_loader.get_budget(
        exchange="coinbase", environment="production"
    )
    coinbase_only = budget_loader.get_exchange_budget("coinbase")

    # Should match exchange budget
    assert exchange_budget.latency_median_ms == coinbase_only.latency_median_ms


def test_unknown_budget_returns_default(budget_loader: BudgetLoader) -> None:
    """Test that unknown budgets return default."""
    unknown_exchange = budget_loader.get_exchange_budget("unknown_exchange")
    default_budget = budget_loader.get_default_budget()

    assert unknown_exchange.latency_median_ms == default_budget.latency_median_ms


def test_list_exchanges(budget_loader: BudgetLoader) -> None:
    """Test listing configured exchanges."""
    exchanges = budget_loader.list_exchanges()

    assert isinstance(exchanges, list)
    assert "coinbase" in exchanges
    assert "binance" in exchanges
    assert "synthetic" in exchanges


def test_list_scenarios(budget_loader: BudgetLoader) -> None:
    """Test listing configured scenarios."""
    scenarios = budget_loader.list_scenarios()

    assert isinstance(scenarios, list)
    assert "flash_crash" in scenarios
    assert "stable_market" in scenarios
    assert "high_volatility" in scenarios


def test_list_environments(budget_loader: BudgetLoader) -> None:
    """Test listing configured environments."""
    environments = budget_loader.list_environments()

    assert isinstance(environments, list)
    assert "production" in environments
    assert "staging" in environments
    assert "development" in environments


def test_list_components(budget_loader: BudgetLoader) -> None:
    """Test listing configured components."""
    components = budget_loader.list_components()

    assert isinstance(components, list)
    assert "ingestion" in components
    assert "execution" in components
    assert "backtest" in components


def test_budget_loader_with_custom_config(tmp_path: Path) -> None:
    """Test loading budget from custom config file."""
    config_path = tmp_path / "custom_budgets.yaml"
    config_path.write_text(
        """
version: "1.0.0"

default:
  latency_median_ms: 100.0
  latency_p95_ms: 200.0
  latency_max_ms: 500.0
  throughput_min_tps: 1.0
  slippage_median_bps: 10.0
  slippage_p95_bps: 30.0

exchanges:
  test_exchange:
    latency_median_ms: 50.0
    latency_p95_ms: 100.0
    latency_max_ms: 200.0
    throughput_min_tps: 5.0
    slippage_median_bps: 5.0
    slippage_p95_bps: 15.0
""",
        encoding="utf-8",
    )

    loader = BudgetLoader(config_path)

    # Check default
    default = loader.get_default_budget()
    assert default.latency_median_ms == 100.0

    # Check custom exchange
    test_exchange = loader.get_exchange_budget("test_exchange")
    assert test_exchange.latency_median_ms == 50.0


def test_budget_loader_missing_config() -> None:
    """Test that missing config raises error."""
    with pytest.raises(FileNotFoundError):
        BudgetLoader(Path("/nonexistent/config.yaml"))


def test_budget_values_are_positive(budget_loader: BudgetLoader) -> None:
    """Test that all budget values are positive."""
    for exchange in budget_loader.list_exchanges():
        budget = budget_loader.get_exchange_budget(exchange)
        assert budget.latency_median_ms > 0
        assert budget.latency_p95_ms > 0
        assert budget.latency_max_ms > 0
        assert budget.throughput_min_tps > 0
        assert budget.slippage_median_bps > 0
        assert budget.slippage_p95_bps > 0


def test_budget_latency_ordering(budget_loader: BudgetLoader) -> None:
    """Test that latency budgets are properly ordered."""
    for exchange in budget_loader.list_exchanges():
        budget = budget_loader.get_exchange_budget(exchange)
        assert budget.latency_median_ms <= budget.latency_p95_ms
        assert budget.latency_p95_ms <= budget.latency_max_ms


def test_budget_slippage_ordering(budget_loader: BudgetLoader) -> None:
    """Test that slippage budgets are properly ordered."""
    for exchange in budget_loader.list_exchanges():
        budget = budget_loader.get_exchange_budget(exchange)
        assert budget.slippage_median_bps <= budget.slippage_p95_bps
