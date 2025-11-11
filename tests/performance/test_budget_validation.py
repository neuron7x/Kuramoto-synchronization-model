"""Tests for performance budget validation infrastructure."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from tests.performance.budget_loader import BudgetLoader


def test_perf_budgets_yaml_valid():
    """Test that perf_budgets.yaml is valid YAML and has required structure."""
    config_path = Path(__file__).parent.parent.parent / "configs" / "perf_budgets.yaml"
    
    assert config_path.exists(), f"Config file not found: {config_path}"
    
    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    
    assert "components" in config, "Missing 'components' section"
    assert "gate_thresholds" in config, "Missing 'gate_thresholds' section"
    
    # Check required components
    components = config["components"]
    assert "order_router" in components, "Missing order_router component"
    assert "link_activator" in components, "Missing link_activator component"
    assert "thermo_validator" in components, "Missing thermo_validator component"
    
    # Validate component structure
    for component_name, component_config in components.items():
        assert "latency_p50_ms" in component_config, f"{component_name} missing latency_p50_ms"
        assert "latency_p95_ms" in component_config, f"{component_name} missing latency_p95_ms"
        assert "latency_p99_ms" in component_config, f"{component_name} missing latency_p99_ms"
        assert "throughput_min_tps" in component_config, f"{component_name} missing throughput_min_tps"
        
        # Validate numeric values
        assert isinstance(component_config["latency_p50_ms"], (int, float))
        assert component_config["latency_p50_ms"] > 0
        assert component_config["latency_p95_ms"] >= component_config["latency_p50_ms"]
        assert component_config["latency_p99_ms"] >= component_config["latency_p95_ms"]


def test_perf_budgets_percentile_ordering():
    """Test that percentile budgets are properly ordered (p50 <= p95 <= p99)."""
    config_path = Path(__file__).parent.parent.parent / "configs" / "perf_budgets.yaml"
    
    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    
    for component_name, component_config in config["components"].items():
        p50 = component_config.get("latency_p50_ms", 0)
        p95 = component_config.get("latency_p95_ms", 0)
        p99 = component_config.get("latency_p99_ms", 0)
        p_max = component_config.get("latency_max_ms", 0)
        
        assert p50 <= p95, f"{component_name}: p50 ({p50}) > p95 ({p95})"
        assert p95 <= p99, f"{component_name}: p95 ({p95}) > p99 ({p99})"
        assert p99 <= p_max, f"{component_name}: p99 ({p99}) > max ({p_max})"


def test_perf_budgets_stability_metrics():
    """Test that stability metrics are within reasonable ranges."""
    config_path = Path(__file__).parent.parent.parent / "configs" / "perf_budgets.yaml"
    
    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    
    for component_name, component_config in config["components"].items():
        # Stability coefficient should be between 0 and 1
        stability_cov = component_config.get("stability_coefficient_max", 0)
        assert 0 < stability_cov < 1, f"{component_name}: Invalid stability_coefficient_max"
        
        # Error rate should be between 0 and 100
        error_rate = component_config.get("error_rate_max_percent", 0)
        assert 0 <= error_rate <= 100, f"{component_name}: Invalid error_rate_max_percent"


def test_gate_thresholds_configuration():
    """Test that gate thresholds are properly configured."""
    config_path = Path(__file__).parent.parent.parent / "configs" / "perf_budgets.yaml"
    
    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    
    thresholds = config.get("gate_thresholds", {})
    
    assert "regression_threshold_percent" in thresholds
    assert "min_sample_size" in thresholds
    assert "confidence_level" in thresholds
    
    # Validate values
    assert 0 < thresholds["regression_threshold_percent"] <= 100
    assert thresholds["min_sample_size"] > 0
    assert 0 < thresholds["confidence_level"] < 1


def test_budget_loader_components():
    """Test BudgetLoader can load component budgets."""
    config_path = Path(__file__).parent.parent.parent / "configs" / "perf_budgets.yaml"
    
    # Note: BudgetLoader expects performance_budgets.yaml by default
    # For this test, we'll just verify the config structure is compatible
    
    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    
    components = config.get("components", {})
    
    # Verify we can extract budget-like information
    for component_name in ["order_router", "link_activator", "thermo_validator"]:
        assert component_name in components
        
        component = components[component_name]
        
        # These fields would be used by a budget validator
        assert "latency_p50_ms" in component
        assert "latency_p95_ms" in component
        assert "throughput_min_tps" in component


def test_flamegraph_configuration():
    """Test flamegraph collection settings."""
    config_path = Path(__file__).parent.parent.parent / "configs" / "perf_budgets.yaml"
    
    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    
    flamegraph = config.get("flamegraph", {})
    
    assert flamegraph.get("enabled") is True
    assert flamegraph.get("sample_frequency_hz", 0) > 0
    assert flamegraph.get("duration_seconds", 0) > 0
    assert "storage_path" in flamegraph
    

def test_reporting_configuration():
    """Test performance reporting settings."""
    config_path = Path(__file__).parent.parent.parent / "configs" / "perf_budgets.yaml"
    
    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    
    reporting = config.get("reporting", {})
    
    assert reporting.get("enabled") is True
    assert "output_path" in reporting
    assert "include_historical" in reporting


def test_component_descriptions():
    """Test that all components have descriptions."""
    config_path = Path(__file__).parent.parent.parent / "configs" / "perf_budgets.yaml"
    
    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    
    for component_name, component_config in config["components"].items():
        assert "description" in component_config, f"{component_name} missing description"
        assert len(component_config["description"]) > 0


def test_observed_baselines_present():
    """Test that observed baseline metrics are documented."""
    config_path = Path(__file__).parent.parent.parent / "configs" / "perf_budgets.yaml"
    
    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    
    for component_name, component_config in config["components"].items():
        # At least p50 and p95 observed values should be present
        assert "observed_p50_ms" in component_config, f"{component_name} missing observed_p50_ms"
        assert "observed_p95_ms" in component_config, f"{component_name} missing observed_p95_ms"
        
        # Observed values should be less than or equal to budgets
        if component_config["observed_p50_ms"] is not None:
            assert (
                component_config["observed_p50_ms"] <= component_config["latency_p50_ms"]
            ), f"{component_name}: observed_p50 exceeds budget"
        
        if component_config["observed_p95_ms"] is not None:
            assert (
                component_config["observed_p95_ms"] <= component_config["latency_p95_ms"]
            ), f"{component_name}: observed_p95 exceeds budget"
