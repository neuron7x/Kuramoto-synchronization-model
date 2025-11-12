"""Tests for configuration validation."""

import pytest
from pydantic import ValidationError
from src.tradepulse_qlw.config import QLWConfig


def test_default_config():
    """Test that default config is valid."""
    cfg = QLWConfig()
    assert cfg.nx > 0, "nx should be positive"
    assert cfg.nt > 0, "nt should be positive"
    assert cfg.gamma_lo < cfg.gamma_hi, "gamma_lo should be less than gamma_hi"


def test_config_validation_bounds():
    """Test configuration validation for out-of-bounds values."""
    # Invalid nx
    with pytest.raises(ValidationError):
        QLWConfig(nx=10)  # Below minimum

    with pytest.raises(ValidationError):
        QLWConfig(nx=10000)  # Above maximum

    # Invalid dt
    with pytest.raises(ValidationError):
        QLWConfig(dt=-0.01)  # Negative

    # Invalid noise_sigma
    with pytest.raises(ValidationError):
        QLWConfig(noise_sigma=2.0)  # Above maximum


def test_config_forbidden_modes():
    """Test forbidden mode options."""
    cfg_static = QLWConfig(forbidden_mode="static")
    assert cfg_static.forbidden_mode == "static"

    cfg_quantile = QLWConfig(forbidden_mode="quantile")
    assert cfg_quantile.forbidden_mode == "quantile"

    cfg_mad = QLWConfig(forbidden_mode="mad")
    assert cfg_mad.forbidden_mode == "mad"

    cfg_pid = QLWConfig(forbidden_mode="pid")
    assert cfg_pid.forbidden_mode == "pid"

    # Invalid mode
    with pytest.raises(ValidationError):
        QLWConfig(forbidden_mode="invalid")


def test_config_serialization():
    """Test config can be serialized to dict."""
    cfg = QLWConfig(nx=256, nt=1024, seed=123)
    cfg_dict = cfg.model_dump()
    assert cfg_dict["nx"] == 256
    assert cfg_dict["nt"] == 1024
    assert cfg_dict["seed"] == 123


def test_config_from_dict():
    """Test config can be created from dict."""
    cfg_dict = {
        "nx": 256,
        "nt": 1024,
        "seed": 123,
        "gamma_lo": 0.1,
        "gamma_hi": 0.5,
    }
    cfg = QLWConfig(**cfg_dict)
    assert cfg.nx == 256
    assert cfg.nt == 1024
    assert cfg.gamma_lo == 0.1
