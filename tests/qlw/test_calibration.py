"""Tests for calibration and MF-DFA functionality."""

import numpy as np
import pytest
from src.tradepulse_qlw.engine import QLWEngine
from src.tradepulse_qlw.config import QLWConfig
from src.tradepulse_qlw.mdfa import hurst_mfdfa, gamma_from_h


def test_gamma_bounds():
    """Test that calibrated gamma stays within configured bounds."""
    cfg = QLWConfig()
    eng = QLWEngine(cfg)
    f = np.random.rand(cfg.nt, 40)
    gamma, meta = eng.calibrate_gamma(f)
    assert cfg.gamma_lo <= gamma <= cfg.gamma_hi, "Gamma should be within bounds"
    assert 0 < meta["H_mean"] < 1, "Hurst exponent should be in (0, 1)"


def test_hurst_estimation():
    """Test Hurst exponent estimation on synthetic data."""
    # Generate persistent series (H > 0.5)
    rng = np.random.default_rng(42)
    ts = np.cumsum(rng.normal(0, 1, 500))
    H = hurst_mfdfa(ts)
    assert 0 < H < 1, "Hurst exponent should be in valid range"


def test_gamma_from_h_mapping():
    """Test gamma mapping from Hurst exponent."""
    gamma_lo, gamma_hi = 0.1, 0.8

    # H=1 (persistent) should give low gamma
    gamma_high_h = gamma_from_h(0.95, gamma_lo, gamma_hi)
    assert gamma_high_h < gamma_hi / 2, "High H should give low gamma"

    # H=0 (anti-persistent) should give high gamma
    gamma_low_h = gamma_from_h(0.05, gamma_lo, gamma_hi)
    assert gamma_low_h > gamma_hi / 2, "Low H should give high gamma"


def test_calibration_stability():
    """Test that calibration is stable across multiple runs."""
    cfg = QLWConfig(seed=42)
    eng = QLWEngine(cfg)

    # Same data should give same results
    rng = np.random.default_rng(42)
    f = rng.normal(0, 1, (cfg.nt, 40))

    gamma1, meta1 = eng.calibrate_gamma(f)
    gamma2, meta2 = eng.calibrate_gamma(f)

    assert np.isclose(gamma1, gamma2), "Calibration should be deterministic"
    assert np.isclose(meta1["H_mean"], meta2["H_mean"]), "H_mean should be stable"
