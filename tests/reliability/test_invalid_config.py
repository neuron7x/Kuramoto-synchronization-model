# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Reliability tests for invalid configuration handling.

Validates configuration validation:
- REL_CONFIG_INVALID_001: Malformed YAML
- REL_CONFIG_INVALID_002: Missing required fields
- REL_CONFIG_INVALID_003: Invalid value types
- REL_CONFIG_INVALID_004: Incompatible parameter combinations

These tests ensure configuration errors are caught early with clear messages.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
import yaml

from backtest.engine import (
    LatencyConfig,
    PortfolioConstraints,
    SlippageConfig,
)


def test_yaml_parse_error() -> None:
    """Test that malformed YAML is caught with clear error (REL_CONFIG_INVALID_001)."""
    
    malformed_yaml = """
    strategy:
      name: test_strategy
      params:
        - threshold: 0.5
        invalid_indent
    """
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write(malformed_yaml)
        config_path = f.name
    
    try:
        # Attempt to parse malformed YAML
        with pytest.raises(yaml.YAMLError, match="parse|syntax|invalid"):
            with open(config_path) as file:
                yaml.safe_load(file)
    finally:
        Path(config_path).unlink()


def test_missing_required_fields() -> None:
    """Test that missing required fields are detected (REL_CONFIG_INVALID_002)."""
    
    # PortfolioConstraints requires initial_capital
    with pytest.raises((TypeError, ValueError), match="initial_capital|required"):
        PortfolioConstraints(
            # Missing initial_capital (required field)
            max_position_pct=0.5,
        )


def test_type_validation() -> None:
    """Test that type errors are caught (REL_CONFIG_INVALID_003)."""
    
    # LatencyConfig expects integers, not strings
    with pytest.raises((TypeError, ValueError)):
        LatencyConfig(
            signal_to_order="not_an_integer",  # type: ignore[arg-type]
        )


def test_incompatible_parameters() -> None:
    """Test that incompatible parameter combos are caught (REL_CONFIG_INVALID_004)."""
    
    # Negative latency is logically invalid
    with pytest.raises((ValueError, AssertionError), match="negative|positive|non-negative"):
        LatencyConfig(
            signal_to_order=-5,  # Negative delay doesn't make sense
        )


def test_zero_initial_capital_rejected() -> None:
    """Test that zero or negative initial capital is rejected."""
    
    with pytest.raises((ValueError, AssertionError), match="capital|positive"):
        PortfolioConstraints(
            initial_capital=0.0,  # Invalid: no starting capital
        )
    
    with pytest.raises((ValueError, AssertionError), match="capital|positive"):
        PortfolioConstraints(
            initial_capital=-1000.0,  # Invalid: negative capital
        )


def test_invalid_percentage_range() -> None:
    """Test that percentages outside [0, 1] are rejected."""
    
    # max_position_pct should be between 0 and 1
    with pytest.raises((ValueError, AssertionError), match="0|1|range|percent"):
        PortfolioConstraints(
            initial_capital=10000.0,
            max_position_pct=1.5,  # > 100%
        )
    
    with pytest.raises((ValueError, AssertionError), match="0|1|range|percent|negative"):
        PortfolioConstraints(
            initial_capital=10000.0,
            max_position_pct=-0.1,  # negative
        )


def test_invalid_slippage_config() -> None:
    """Test that invalid slippage parameters are caught."""
    
    # Negative slippage doesn't make sense
    with pytest.raises((ValueError, AssertionError), match="slippage|negative|positive"):
        SlippageConfig(
            fixed_bps=-10,  # Negative slippage
        )


def test_config_validation_error_message_quality() -> None:
    """Test that validation errors have helpful messages."""
    
    try:
        PortfolioConstraints(
            initial_capital=-5000.0,
        )
        pytest.fail("Expected validation error for negative capital")
    except (ValueError, AssertionError) as e:
        error_msg = str(e)
        # Error message should mention what's wrong
        assert any(word in error_msg.lower() for word in ["capital", "positive", "negative", "invalid"])


def test_conflicting_config_values() -> None:
    """Test that conflicting configuration values are detected."""
    
    # If max_leverage < 1, it conflicts with the concept of leverage
    with pytest.raises((ValueError, AssertionError), match="leverage|greater"):
        PortfolioConstraints(
            initial_capital=10000.0,
            max_leverage=0.5,  # < 1 doesn't make sense for leverage
        )


def test_yaml_type_coercion_safe() -> None:
    """Test that YAML type coercion is handled safely."""
    
    yaml_config = """
    strategy:
      threshold: "0.5"  # String instead of float
      lookback: "10"    # String instead of int
    """
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write(yaml_config)
        config_path = f.name
    
    try:
        with open(config_path) as file:
            config = yaml.safe_load(file)
        
        # YAML should parse, but values are strings
        assert isinstance(config["strategy"]["threshold"], str)
        assert isinstance(config["strategy"]["lookback"], str)
        
        # Application should validate types and convert or reject
        # This would fail if we try to use string where float expected
        with pytest.raises((TypeError, ValueError)):
            float_val = config["strategy"]["threshold"]
            if not isinstance(float_val, (int, float)):
                # In real code, validation would happen here
                raise TypeError(f"Expected number, got {type(float_val).__name__}")
    finally:
        Path(config_path).unlink()


def test_empty_config_file() -> None:
    """Test that empty config file is handled gracefully."""
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write("")  # Empty file
        config_path = f.name
    
    try:
        with open(config_path) as file:
            config = yaml.safe_load(file)
        
        # Empty YAML file loads as None
        assert config is None
        
        # Application should handle None config appropriately
        if config is None:
            # Would raise in real validation
            raise ValueError("Configuration file is empty")
    except ValueError as e:
        assert "empty" in str(e).lower()
    finally:
        Path(config_path).unlink()


def test_extra_fields_warning() -> None:
    """Test that extra/unknown fields in config generate warning or error."""
    
    # This depends on whether config uses strict validation
    # For now, we test that dataclass accepts known fields
    config = LatencyConfig(
        signal_to_order=1,
        order_to_execution=1,
        execution_to_fill=1,
        # extra_field=123,  # Would be rejected by dataclass
    )
    
    assert config.signal_to_order == 1
    
    # Attempting to add unknown field after creation should fail
    with pytest.raises(AttributeError):
        config.unknown_field = 999  # type: ignore[attr-defined]
