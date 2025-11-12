"""Tests for QLW engine integration."""

import numpy as np
import pytest
from src.tradepulse_qlw.engine import QLWEngine
from src.tradepulse_qlw.config import QLWConfig


def test_engine_basic_run():
    """Test basic engine execution."""
    cfg = QLWConfig(nx=64, nt=128, seed=42)
    eng = QLWEngine(cfg)

    # Generate synthetic features
    rng = np.random.default_rng(42)
    features = rng.normal(1.0, 0.1, (cfg.nt, 40))

    result = eng.run(features)

    # Check result structure
    assert result.psi.shape == (cfg.nt, cfg.nx), "Wave field shape incorrect"
    assert result.resonance.shape[0] == cfg.nt, "Resonance array shape incorrect"
    assert result.forbidden_mask.shape == (cfg.nt, cfg.nx), "Forbidden mask shape incorrect"
    assert result.soft_mask.shape == (cfg.nt, cfg.nx), "Soft mask shape incorrect"
    assert "gamma" in result.meta, "Meta should contain gamma"
    assert "tau" in result.meta, "Meta should contain tau"


def test_engine_with_orderbook():
    """Test engine with order book data."""
    cfg = QLWConfig(nx=64, nt=128, seed=42)
    eng = QLWEngine(cfg)

    rng = np.random.default_rng(42)
    features = rng.normal(1.0, 0.1, (cfg.nt, 40))
    orderbook = rng.uniform(0.5, 1.5, (cfg.nt, 10, 2))

    result = eng.run(features, orderbook=orderbook)

    assert result.meta["c"] >= cfg.c_min, "Wave speed should be above minimum"
    assert result.meta["c"] <= cfg.c_max, "Wave speed should be below maximum"


def test_engine_with_delta_volume():
    """Test engine with volume delta."""
    cfg = QLWConfig(nx=64, nt=128, seed=42)
    eng = QLWEngine(cfg)

    rng = np.random.default_rng(42)
    features = rng.normal(1.0, 0.1, (cfg.nt, 40))
    delta_vol = rng.normal(0, 0.1, cfg.nt)

    result = eng.run(features, delta_volume=delta_vol)

    assert result.psi.shape == (cfg.nt, cfg.nx), "Wave field shape incorrect"


def test_forbidden_modes():
    """Test different forbidden zone computation modes."""
    cfg_quantile = QLWConfig(nx=64, nt=128, forbidden_mode="quantile", seed=42)
    cfg_mad = QLWConfig(nx=64, nt=128, forbidden_mode="mad", seed=42)
    cfg_pid = QLWConfig(nx=64, nt=128, forbidden_mode="pid", seed=42)

    rng = np.random.default_rng(42)
    features = rng.normal(1.0, 0.1, (128, 40))

    eng_q = QLWEngine(cfg_quantile)
    result_q = eng_q.run(features)

    eng_m = QLWEngine(cfg_mad)
    result_m = eng_m.run(features)

    eng_p = QLWEngine(cfg_pid)
    result_p = eng_p.run(features)

    # All should produce valid tau
    assert result_q.meta["tau"] > 0, "Quantile tau should be positive"
    assert result_m.meta["tau"] > 0, "MAD tau should be positive"
    assert result_p.meta["tau"] > 0, "PID tau should be positive"


def test_tacl_gate_trigger():
    """Test TACL gate trigger logic."""
    cfg = QLWConfig(nx=64, nt=128, seed=42)
    eng = QLWEngine(cfg)

    rng = np.random.default_rng(42)
    features = rng.normal(1.0, 0.1, (cfg.nt, 40))

    result = eng.run(features)

    # Check that hard_gate_trigger is a boolean array
    assert "hard_gate_trigger" in result.meta, "Should have hard_gate_trigger"
    trigger = result.meta["hard_gate_trigger"]
    assert isinstance(trigger, (np.ndarray, bool, np.bool_)), "Trigger should be array or bool"


def test_meta_completeness():
    """Test that all expected metadata is present."""
    cfg = QLWConfig(nx=64, nt=128, seed=42)
    eng = QLWEngine(cfg)

    rng = np.random.default_rng(42)
    features = rng.normal(1.0, 0.1, (cfg.nt, 40))

    result = eng.run(features)

    required_keys = [
        "dt",
        "dx",
        "c",
        "c_mean",
        "gamma",
        "cfl",
        "seed",
        "eta_sigma",
        "tau",
        "pml_gain",
        "R_auc",
        "H_mean",
        "H_std",
    ]

    for key in required_keys:
        assert key in result.meta, f"Meta should contain {key}"
