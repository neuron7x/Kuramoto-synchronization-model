"""Tests for tacl.release_gates module."""

from __future__ import annotations

from pathlib import Path
from tempfile import NamedTemporaryFile

import pytest
import yaml

from tacl.release_gates import _load_perf_budgets


def test_load_perf_budgets_legacy_format():
    """Test loading performance budgets with legacy format (observed_ms/budget_ms)."""
    legacy_config = {
        "components": {
            "test_component": {
                "observed_ms": 50.0,
                "budget_ms": 75.0,
            }
        }
    }
    
    with NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(legacy_config, f)
        temp_path = Path(f.name)
    
    try:
        budgets = _load_perf_budgets(temp_path)
        
        assert len(budgets) == 1
        assert budgets[0].component == "test_component"
        assert budgets[0].observed_ms == 50.0
        assert budgets[0].budget_ms == 75.0
        assert budgets[0].passed() is True
    finally:
        temp_path.unlink()


def test_load_perf_budgets_new_format():
    """Test loading performance budgets with new percentile-based format."""
    new_config = {
        "version": "2.0.0",
        "components": {
            "test_component": {
                "description": "Test component",
                "latency_p50_ms": 40.0,
                "latency_p95_ms": 75.0,
                "latency_p99_ms": 100.0,
                "observed_p50_ms": 35.0,
                "observed_p95_ms": 50.0,
                "observed_p99_ms": 80.0,
                "throughput_min_tps": 100.0,
            }
        }
    }
    
    with NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(new_config, f)
        temp_path = Path(f.name)
    
    try:
        budgets = _load_perf_budgets(temp_path)
        
        assert len(budgets) == 1
        assert budgets[0].component == "test_component"
        # New format uses observed_p95_ms and latency_p95_ms
        assert budgets[0].observed_ms == 50.0
        assert budgets[0].budget_ms == 75.0
        assert budgets[0].passed() is True
    finally:
        temp_path.unlink()


def test_load_perf_budgets_new_format_exceeds_budget():
    """Test that budget violations are detected with new format."""
    new_config = {
        "components": {
            "slow_component": {
                "latency_p95_ms": 50.0,
                "observed_p95_ms": 75.0,  # Exceeds budget
            }
        }
    }
    
    with NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(new_config, f)
        temp_path = Path(f.name)
    
    try:
        budgets = _load_perf_budgets(temp_path)
        
        assert len(budgets) == 1
        assert budgets[0].component == "slow_component"
        assert budgets[0].observed_ms == 75.0
        assert budgets[0].budget_ms == 50.0
        assert budgets[0].passed() is False  # Should fail budget check
    finally:
        temp_path.unlink()


def test_load_perf_budgets_multiple_components():
    """Test loading multiple components in both formats."""
    mixed_config = {
        "components": {
            "legacy_comp": {
                "observed_ms": 30.0,
                "budget_ms": 50.0,
            },
            "new_comp": {
                "latency_p95_ms": 100.0,
                "observed_p95_ms": 85.0,
            }
        }
    }
    
    with NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(mixed_config, f)
        temp_path = Path(f.name)
    
    try:
        budgets = _load_perf_budgets(temp_path)
        
        assert len(budgets) == 2
        
        # Find each component
        legacy = next(b for b in budgets if b.component == "legacy_comp")
        new = next(b for b in budgets if b.component == "new_comp")
        
        # Legacy format
        assert legacy.observed_ms == 30.0
        assert legacy.budget_ms == 50.0
        assert legacy.passed() is True
        
        # New format
        assert new.observed_ms == 85.0
        assert new.budget_ms == 100.0
        assert new.passed() is True
    finally:
        temp_path.unlink()


def test_load_perf_budgets_from_actual_config():
    """Test loading from the actual perf_budgets.yaml config file."""
    # This test verifies that the real config file can be loaded
    config_path = Path(__file__).parent.parent.parent / "configs" / "perf_budgets.yaml"
    
    if not config_path.exists():
        pytest.skip("perf_budgets.yaml not found")
    
    budgets = _load_perf_budgets(config_path)
    
    # Should have at least the three main components
    assert len(budgets) >= 3
    
    component_names = {b.component for b in budgets}
    assert "order_router" in component_names
    assert "link_activator" in component_names
    assert "thermo_validator" in component_names
    
    # All budgets should have valid numeric values
    for budget in budgets:
        assert budget.observed_ms >= 0
        assert budget.budget_ms > 0
        assert isinstance(budget.passed(), bool)
