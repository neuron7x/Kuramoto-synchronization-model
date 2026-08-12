# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Performance budget configuration loader.

This module provides utilities to load performance budgets from YAML configuration.
"""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

import yaml

from .multi_exchange_replay import PerformanceBudget


class BudgetLoader:
    """Load and manage performance budgets from configuration."""

    def __init__(self, config_path: Path | None = None) -> None:
        """Initialize budget loader.

        Args:
            config_path: Path to budget configuration YAML file.
                        If None, uses default config.
        """
        if config_path is None:
            config_path = (
                Path(__file__).resolve().parent.parent.parent
                / "configs"
                / "performance_budgets.yaml"
            )

        self.config_path = config_path
        self._config: dict = {}
        self._load_config()

    def _load_config(self) -> None:
        """Load configuration from YAML file."""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Budget config not found: {self.config_path}")

        with open(self.config_path, "r", encoding="utf-8") as f:
            self._config = yaml.safe_load(f)

    def get_default_budget(self) -> PerformanceBudget:
        """Get the default performance budget.

        Returns:
            Default performance budget
        """
        return self._create_budget(self._config.get("default", {}))

    def get_exchange_budget(self, exchange: str) -> PerformanceBudget:
        """Get performance budget for specific exchange.

        Args:
            exchange: Exchange name (e.g., 'coinbase', 'binance')

        Returns:
            Exchange-specific budget or default if not found
        """
        exchanges = self._config.get("exchanges", {})
        if exchange in exchanges:
            return self._create_budget(exchanges[exchange])
        return self.get_default_budget()

    def get_scenario_budget(self, scenario: str) -> PerformanceBudget:
        """Get performance budget for specific scenario.

        Args:
            scenario: Scenario name (e.g., 'flash_crash', 'stable_market')

        Returns:
            Scenario-specific budget or default if not found
        """
        scenarios = self._config.get("scenarios", {})
        if scenario in scenarios:
            return self._create_budget(scenarios[scenario])
        return self.get_default_budget()

    def get_environment_budget(self, environment: str) -> PerformanceBudget:
        """Get performance budget for specific environment.

        Args:
            environment: Environment name (e.g., 'production', 'staging')

        Returns:
            Environment-specific budget or default if not found
        """
        environments = self._config.get("environments", {})
        if environment in environments:
            return self._create_budget(environments[environment])
        return self.get_default_budget()

    def get_component_budget(self, component: str) -> PerformanceBudget:
        """Get performance budget for specific component.

        Args:
            component: Component name (e.g., 'ingestion', 'execution')

        Returns:
            Component-specific budget or default if not found
        """
        components = self._config.get("components", {})
        if component in components:
            return self._create_budget(components[component])
        return self.get_default_budget()

    def get_budget(
        self,
        exchange: str | None = None,
        scenario: str | None = None,
        environment: str | None = None,
        component: str | None = None,
    ) -> PerformanceBudget:
        """Get performance budget with fallback priority.

        Priority order:
        1. Scenario-specific (if provided)
        2. Exchange-specific (if provided)
        3. Environment-specific (if provided)
        4. Component-specific (if provided)
        5. Default

        Args:
            exchange: Optional exchange name
            scenario: Optional scenario name
            environment: Optional environment name
            component: Optional component name

        Returns:
            Most specific applicable budget
        """
        if scenario:
            scenarios = self._config.get("scenarios", {})
            if scenario in scenarios:
                return self._create_budget(scenarios[scenario])

        if exchange:
            exchanges = self._config.get("exchanges", {})
            if exchange in exchanges:
                return self._create_budget(exchanges[exchange])

        if environment:
            environments = self._config.get("environments", {})
            if environment in environments:
                return self._create_budget(environments[environment])

        if component:
            components = self._config.get("components", {})
            if component in components:
                return self._create_budget(components[component])

        return self.get_default_budget()

    def list_exchanges(self) -> list[str]:
        """List all configured exchanges.

        Returns:
            List of exchange names
        """
        return list(self._config.get("exchanges", {}).keys())

    def list_scenarios(self) -> list[str]:
        """List all configured scenarios.

        Returns:
            List of scenario names
        """
        return list(self._config.get("scenarios", {}).keys())

    def list_environments(self) -> list[str]:
        """List all configured environments.

        Returns:
            List of environment names
        """
        return list(self._config.get("environments", {}).keys())

    def list_components(self) -> list[str]:
        """List all configured components.

        Returns:
            List of component names
        """
        return list(self._config.get("components", {}).keys())

    @staticmethod
    def _create_budget(config: Mapping) -> PerformanceBudget:
        """Create PerformanceBudget from configuration dict.

        Args:
            config: Configuration dictionary

        Returns:
            PerformanceBudget instance
        """
        return PerformanceBudget(
            latency_median_ms=float(config.get("latency_median_ms", 60.0)),
            latency_p95_ms=float(config.get("latency_p95_ms", 100.0)),
            latency_max_ms=float(config.get("latency_max_ms", 200.0)),
            throughput_min_tps=float(config.get("throughput_min_tps", 5.0)),
            slippage_median_bps=float(config.get("slippage_median_bps", 5.0)),
            slippage_p95_bps=float(config.get("slippage_p95_bps", 15.0)),
        )


__all__ = ["BudgetLoader"]
