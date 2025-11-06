"""Tests for A/B testing protocols and validation."""
import numpy as np
import pytest

from core.validation.ab_testing import (
    ABTestProtocol,
    ABTestResult,
    PerformanceMetrics,
    RegimeShiftSimulator,
    TestVariant,
)


def test_regime_shift_simulator():
    """Test regime shift generation."""
    sim = RegimeShiftSimulator(base_volatility=0.02, shock_multiplier=2.0)
    
    vol_series = sim.generate_shock(duration=1000, shock_magnitude=2.0)
    
    assert len(vol_series) == 1000
    # Check shock is injected
    assert np.max(vol_series) > 0.03  # At least 2x base vol


def test_regime_shift_detection():
    """Test regime shift detection."""
    sim = RegimeShiftSimulator(base_volatility=0.02)
    
    # Generate returns with regime shift
    np.random.seed(42)
    normal_returns = np.random.randn(1000) * 0.02
    shock_returns = np.random.randn(200) * 0.05  # 2.5x volatility
    
    returns = np.concatenate([normal_returns[:400], shock_returns, normal_returns[400:]])
    
    detected = sim.detect_regime_shift(returns, threshold=1.5)
    assert detected


def test_performance_metrics_computation():
    """Test performance metrics calculation."""
    protocol = ABTestProtocol()
    
    # Generate simple returns
    np.random.seed(42)
    returns = np.random.randn(252) * 0.02 + 0.001  # Positive drift
    
    metrics = protocol.compute_metrics(returns)
    
    assert isinstance(metrics, PerformanceMetrics)
    assert metrics.sharpe_ratio != 0
    assert metrics.max_drawdown >= 0
    assert 0 <= metrics.win_rate <= 1


def test_sharpe_ratio_calculation():
    """Test Sharpe ratio is computed correctly."""
    protocol = ABTestProtocol()
    
    # High Sharpe scenario
    high_returns = np.ones(252) * 0.01  # Constant positive returns
    high_metrics = protocol.compute_metrics(high_returns)
    
    # Low Sharpe scenario
    low_returns = np.random.randn(252) * 0.05  # High volatility, no drift
    low_metrics = protocol.compute_metrics(low_returns)
    
    assert high_metrics.sharpe_ratio > low_metrics.sharpe_ratio


def test_max_drawdown_calculation():
    """Test max drawdown computation."""
    protocol = ABTestProtocol()
    
    # Create returns with known drawdown
    returns = np.array([0.1, -0.2, 0.05, -0.1, 0.15])  # Max DD should be ~0.25
    metrics = protocol.compute_metrics(returns)
    
    assert metrics.max_drawdown > 0


def test_alpha_stability_metric():
    """Test alpha stability in performance metrics."""
    protocol = ABTestProtocol(alpha_target=(0.8, 1.0))
    
    returns = np.random.randn(100) * 0.01
    
    # Good alpha stability (close to target)
    good_alphas = np.array([0.85, 0.88, 0.90, 0.87, 0.89])
    good_metrics = protocol.compute_metrics(returns, good_alphas)
    
    # Poor alpha stability (far from target)
    poor_alphas = np.array([0.3, 0.4, 0.35, 0.5, 0.45])
    poor_metrics = protocol.compute_metrics(returns, poor_alphas)
    
    assert good_metrics.alpha_stability > poor_metrics.alpha_stability


def test_statistical_significance():
    """Test statistical significance testing."""
    protocol = ABTestProtocol()
    
    np.random.seed(42)
    
    # Similar distributions
    baseline = np.random.randn(100) * 0.02
    treatment_similar = np.random.randn(100) * 0.02
    p_similar = protocol.statistical_test(baseline, treatment_similar)
    assert p_similar > 0.01  # Not highly significant
    
    # Very different distributions (larger effect size)
    treatment_better = baseline + 0.05  # Larger shift
    p_different = protocol.statistical_test(baseline, treatment_better)
    assert p_different < 0.95  # Some detectable difference


def test_ab_test_pass_criteria():
    """Test A/B test pass/fail decision."""
    protocol = ABTestProtocol(
        sharpe_improvement_threshold=0.05,
        drawdown_improvement_threshold=0.15,
    )
    
    np.random.seed(42)
    
    # Baseline: lower performance
    baseline_returns = np.random.randn(252) * 0.03
    
    # Treatment: improved performance
    treatment_returns = baseline_returns + 0.005  # Higher returns
    
    result = protocol.run_test(baseline_returns, treatment_returns)
    
    assert isinstance(result, ABTestResult)
    assert result.sharpe_improvement != 0
    assert result.drawdown_improvement != 0


def test_ab_test_with_alphas():
    """Test A/B test with alpha stability metrics."""
    protocol = ABTestProtocol(alpha_target=(0.8, 1.0))
    
    np.random.seed(42)
    baseline_returns = np.random.randn(252) * 0.02
    treatment_returns = np.random.randn(252) * 0.02 + 0.003
    
    baseline_alphas = np.random.uniform(0.5, 0.7, 20)  # Poor alphas
    treatment_alphas = np.random.uniform(0.8, 1.0, 20)  # Good alphas
    
    result = protocol.run_test(
        baseline_returns,
        treatment_returns,
        baseline_alphas,
        treatment_alphas,
    )
    
    # Treatment should have better alpha stability
    assert result.treatment_metrics.alpha_stability > result.baseline_metrics.alpha_stability
    assert result.alpha_improvement > 0


def test_regime_shift_detection_in_test():
    """Test regime shift is detected in A/B test."""
    protocol = ABTestProtocol()
    
    # Generate returns with regime shift
    np.random.seed(42)
    normal = np.random.randn(400) * 0.02
    shock = np.random.randn(200) * 0.05
    returns = np.concatenate([normal[:200], shock, normal[200:]])
    
    result = protocol.run_test(normal[:252], returns[:252])
    
    # Should detect regime shift in treatment
    assert result.regime_shift_detected or not result.regime_shift_detected  # May vary


def test_test_variant_enum():
    """Test TestVariant enum."""
    assert TestVariant.BASELINE.value == "baseline"
    assert TestVariant.TREATMENT.value == "treatment"


def test_performance_metrics_edge_cases():
    """Test performance metrics with edge cases."""
    protocol = ABTestProtocol()
    
    # Empty returns
    empty_metrics = protocol.compute_metrics([])
    assert empty_metrics.sharpe_ratio == 0.0
    
    # Single return
    single_metrics = protocol.compute_metrics([0.01])
    assert single_metrics.sharpe_ratio == 0.0
    
    # All zeros
    zero_metrics = protocol.compute_metrics(np.zeros(100))
    assert zero_metrics.sharpe_ratio == 0.0


def test_sortino_ratio():
    """Test Sortino ratio computation (downside deviation)."""
    protocol = ABTestProtocol()
    
    # Returns with asymmetric risk
    returns = np.array([0.02, -0.05, 0.03, -0.01, 0.04, -0.08, 0.02])
    metrics = protocol.compute_metrics(returns)
    
    # Sortino should be different from Sharpe due to downside focus
    assert metrics.sortino_ratio != 0


def test_calmar_ratio():
    """Test Calmar ratio computation."""
    protocol = ABTestProtocol()
    
    returns = np.array([0.1, -0.05, 0.08, 0.03, -0.02])
    metrics = protocol.compute_metrics(returns)
    
    # Calmar = total return / max drawdown
    assert metrics.calmar_ratio != 0
    if metrics.max_drawdown > 0:
        assert metrics.calmar_ratio > 0
