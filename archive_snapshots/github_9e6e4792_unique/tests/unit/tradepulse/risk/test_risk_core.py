"""Tests for risk core module."""

# Import directly from module file
import importlib.util
from pathlib import Path

import numpy as np
import pytest

spec = importlib.util.spec_from_file_location(
    "risk_core",
    Path(__file__).parent.parent.parent.parent.parent
    / "src/tradepulse/risk/risk_core.py",
)
risk_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(risk_module)

var_es = risk_module.var_es
kelly_shrink = risk_module.kelly_shrink
compute_final_size = risk_module.compute_final_size
check_risk_breach = risk_module.check_risk_breach
RiskConfig = risk_module.RiskConfig


class TestVarES:
    """Test VaR and ES calculations."""

    def test_normal_returns(self):
        """Test VaR/ES on normal distributed returns."""
        np.random.seed(42)
        returns = np.random.randn(1000) * 0.02

        var, es = var_es(returns, alpha=0.95)

        assert var > 0
        assert es > 0
        assert es >= var

    def test_handles_non_finite_inputs(self):
        """Non-finite inputs should be ignored safely."""
        returns = np.array([0.01, np.nan, 0.02, np.inf, -0.03])

        var, es = var_es(returns, alpha=0.95)

        assert np.isfinite(var)
        assert np.isfinite(es)
        assert es >= var


class TestKellyShrink:
    """Test Kelly fraction with shrinkage."""

    def test_emergent_no_shrink(self):
        """Test EMERGENT state with no shrinkage."""
        f = kelly_shrink(0.001, 0.0004, "EMERGENT", 1.0)
        assert abs(f - 1.0) < 0.01

    def test_caution_half_shrink(self):
        """Test CAUTION state with half shrinkage."""
        f = kelly_shrink(0.001, 0.0004, "CAUTION", 1.0)
        assert abs(f - 0.5) < 0.01

    def test_kill_zero_size(self):
        """Test KILL state with zero sizing."""
        f = kelly_shrink(0.001, 0.0004, "KILL", 1.0)
        assert f == 0.0


class TestComputeFinalSize:
    """Test final size computation."""

    def test_basic_sizing(self):
        """Test basic size computation."""
        size = compute_final_size(0.8, 0.5, 1.0)
        assert abs(size - 0.4) < 0.01


class TestCheckRiskBreach:
    """Test risk breach checking."""

    def test_no_breach(self):
        """Test when ES is below limit."""
        state = check_risk_breach(0.02, 0.03)
        assert state == "OK"

    def test_breach(self):
        """Test when ES exceeds limit."""
        state = check_risk_breach(0.04, 0.03)
        assert state == "BREACH"

    def test_non_finite_es_flags_breach(self):
        """Non-finite ES should be treated as a breach for safety."""
        state = check_risk_breach(float("nan"), 0.03)
        assert state == "BREACH"


class TestRiskConfig:
    """Test risk configuration handling."""

    def test_respects_zero_overrides(self, monkeypatch):
        """Explicit zero values should not fall back to env defaults."""
        monkeypatch.setenv("TP_ES_LIMIT", "0.10")
        monkeypatch.setenv("TP_VAR_ALPHA", "0.90")
        monkeypatch.setenv("TP_FMAX", "0.50")

        cfg = RiskConfig(es_limit=0.0, var_alpha=0.0, f_max=0.0)

        assert cfg.es_limit == 0.0
        assert cfg.var_alpha == 0.0
        assert cfg.f_max == 0.0

    def test_env_defaults_used_when_none(self, monkeypatch):
        """Environment variables should provide defaults when params omitted."""
        monkeypatch.setenv("TP_ES_LIMIT", "0.07")
        monkeypatch.setenv("TP_VAR_ALPHA", "0.93")
        monkeypatch.setenv("TP_FMAX", "0.75")

        cfg = RiskConfig()

        assert cfg.es_limit == pytest.approx(0.07)
        assert cfg.var_alpha == pytest.approx(0.93)
        assert cfg.f_max == pytest.approx(0.75)
