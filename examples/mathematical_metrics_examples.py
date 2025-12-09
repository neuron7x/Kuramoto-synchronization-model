#!/usr/bin/env python3
"""Examples demonstrating mathematical metrics and their interpretations.

This script provides practical examples of using TradePulse's mathematical
metrics for signal analysis, risk assessment, and market regime detection.

Run this script to see interactive examples:
    python examples/mathematical_metrics_examples.py
"""

from __future__ import annotations

import numpy as np

# Core mathematical metrics
from core.metrics.dfa import dfa_alpha
from core.metrics.aperiodic import aperiodic_slope
from core.metrics.lyapunov import eoi_edge_of_instability

# Backtest performance metrics
from backtest.performance import compute_performance_metrics

# Risk metrics
from src.tradepulse.risk.risk_core import var_es, kelly_shrink

# Utilities
from utils.fractal_cascade import pink_noise

# Check if optional dependencies are available
try:
    from core.metrics.holder import (
        holder_exponent_wavelet,
        multifractal_width,
    )
    PYWT_AVAILABLE = True
except RuntimeError:
    PYWT_AVAILABLE = False
    print("⚠️  PyWavelets not installed - Hölder exponent examples will be skipped")
    print("    Install with: pip install PyWavelets\n")


def example_dfa_analysis():
    """Demonstrate DFA for detecting long-range correlations."""
    print("=" * 70)
    print("Example 1: Detrended Fluctuation Analysis (DFA)")
    print("=" * 70)
    print("\nDFA measures long-range correlations in time series.")
    print("α ≈ 0.5: uncorrelated (white noise)")
    print("α > 0.5: persistent (trending)")
    print("α < 0.5: anti-persistent (mean-reverting)")
    print()

    # Generate different types of noise
    np.random.seed(42)
    n = 4096

    # White noise (uncorrelated)
    white_noise = np.random.randn(n)
    alpha_white = dfa_alpha(white_noise, min_win=50, max_win=1000, n_win=12)
    print(f"White noise:     α = {alpha_white:.3f} (expected ≈ 0.5)")

    # Pink noise (1/f, persistent)
    pink = pink_noise(n, beta=1.0)
    alpha_pink = dfa_alpha(pink, min_win=50, max_win=1000, n_win=12)
    print(f"Pink noise:      α = {alpha_pink:.3f} (expected ≈ 1.0)")

    # Random walk (very persistent)
    random_walk = np.cumsum(np.random.randn(n))
    alpha_walk = dfa_alpha(random_walk, min_win=50, max_win=1000, n_win=12)
    print(f"Random walk:     α = {alpha_walk:.3f} (expected ≈ 1.5)")

    # Anti-correlated signal
    anti_corr = np.array([(-1) ** i * np.random.randn() for i in range(n)])
    alpha_anti = dfa_alpha(anti_corr, min_win=50, max_win=1000, n_win=12)
    print(f"Anti-correlated: α = {alpha_anti:.3f} (expected < 0.5)")

    print("\n💡 Trading Application:")
    print("   α > 0.65: Trending regime → momentum strategies")
    print("   α < 0.35: Mean-reverting → contrarian strategies")
    print("   0.35 ≤ α ≤ 0.65: Random walk → reduce position sizes")
    print()


def example_aperiodic_slope():
    """Demonstrate aperiodic slope for characterizing noise color."""
    print("=" * 70)
    print("Example 2: Aperiodic Spectral Slope (1/f^β analysis)")
    print("=" * 70)
    print("\nThe slope m in log₁₀(PSD) vs log₁₀(f) characterizes noise color:")
    print("m ≈ 0:  White noise (flat spectrum)")
    print("m ≈ -1: Pink noise (1/f)")
    print("m ≈ -2: Brown noise (1/f²)")
    print()

    np.random.seed(42)
    n = 4096
    fs = 100.0  # 100 Hz sampling

    # White noise
    white = np.random.randn(n)
    slope_white = aperiodic_slope(white, fs=fs, f_lo=0.5, f_hi=40.0)
    print(f"White noise: slope = {slope_white:.3f} (expected ≈ 0)")

    # Pink noise
    pink = pink_noise(n, beta=1.0)
    slope_pink = aperiodic_slope(pink, fs=fs, f_lo=0.5, f_hi=40.0)
    print(f"Pink noise:  slope = {slope_pink:.3f} (expected ≈ -1)")

    # Brown noise (integrated white noise)
    brown = np.cumsum(np.random.randn(n))
    slope_brown = aperiodic_slope(brown, fs=fs, f_lo=0.5, f_hi=40.0)
    print(f"Brown noise: slope = {slope_brown:.3f} (expected ≈ -2)")

    print("\n💡 Trading Application:")
    print("   Slope ≈ -1: Healthy market dynamics (1/f noise)")
    print("   Slope < -1.5: Excessive smoothness → potential mean reversion")
    print("   Slope > -0.5: Too much high-frequency noise → reduce sampling frequency")
    print()


def example_holder_exponent():
    """Demonstrate Hölder exponent for signal regularity."""
    if not PYWT_AVAILABLE:
        print("⚠️  Skipping Hölder exponent example (PyWavelets not installed)\n")
        return

    print("=" * 70)
    print("Example 3: Hölder Exponent (Local Regularity)")
    print("=" * 70)
    print("\nHölder exponent H measures local smoothness:")
    print("H > 1:   Very smooth (differentiable)")
    print("H ≈ 0.5: Brownian-like")
    print("H < 0.5: Rough/singular")
    print()

    np.random.seed(42)
    n = 2048

    # Smooth signal (sinusoid)
    t = np.linspace(0, 10 * np.pi, n)
    smooth = np.sin(t) + 0.1 * np.sin(5 * t)
    h_smooth = holder_exponent_wavelet(smooth)
    print(f"Smooth sinusoid:   H = {h_smooth:.3f} (expected > 0.5)")

    # Random walk (H ≈ 0.5-1.0)
    walk = np.cumsum(np.random.randn(n))
    h_walk = holder_exponent_wavelet(walk)
    print(f"Random walk:       H = {h_walk:.3f} (expected 0.5-1.0)")

    # Rough signal (white noise)
    rough = np.random.randn(n)
    h_rough = holder_exponent_wavelet(rough)
    print(f"White noise:       H = {h_rough:.3f} (expected < 0.5)")

    # Multifractal width
    multifractal = np.cumsum(pink_noise(n, beta=1.0))
    width = multifractal_width(multifractal)
    print(f"\nMultifractal width: Δh = {width:.3f}")
    print("  (Δh > 0.2 indicates significant multifractality)")

    print("\n💡 Trading Application:")
    print("   H > 0.7: Smooth trending → momentum works well")
    print("   H < 0.3: Very rough → increase filters, wider stops")
    print("   Large Δh: Multifractal → regime-dependent strategies")
    print()


def example_edge_of_instability():
    """Demonstrate EOI metric for learning dynamics."""
    print("=" * 70)
    print("Example 4: Edge of Instability (Gradient Dynamics)")
    print("=" * 70)
    print("\nEOI measures lag-1 autocorrelation of gradient norms:")
    print("EOI ≈ 0:   Uncorrelated (good exploration)")
    print("EOI > 0.5: Strong persistence (momentum)")
    print("|EOI| ≈ 1: Instability risk")
    print()

    np.random.seed(42)
    n = 500

    # Stable regime (white noise gradients)
    stable_grads = np.abs(np.random.randn(n))
    eoi_stable = eoi_edge_of_instability(stable_grads, win=200)
    print(f"Stable regime:      EOI = {eoi_stable:.3f}")

    # Momentum regime (AR(1) gradients)
    momentum_grads = np.zeros(n)
    momentum_grads[0] = np.random.randn()
    for i in range(1, n):
        momentum_grads[i] = 0.7 * momentum_grads[i-1] + 0.3 * np.random.randn()
    momentum_grads = np.abs(momentum_grads)
    eoi_momentum = eoi_edge_of_instability(momentum_grads, win=200)
    print(f"Momentum regime:    EOI = {eoi_momentum:.3f}")

    # Oscillatory (negative autocorrelation)
    oscillatory = np.array([(-1) ** i * abs(np.random.randn()) for i in range(n)])
    eoi_osc = eoi_edge_of_instability(oscillatory, win=200)
    print(f"Oscillatory regime: EOI = {eoi_osc:.3f}")

    print("\n💡 Trading Application:")
    print("   |EOI| < 0.3: Good for exploration, try new strategies")
    print("   EOI > 0.6: Strong momentum → trend-following may work")
    print("   EOI < -0.6: Oscillations → reduce frequency, wider filters")
    print()


def example_performance_metrics():
    """Demonstrate backtest performance metrics."""
    print("=" * 70)
    print("Example 5: Performance Metrics (Sharpe, Sortino, PSR)")
    print("=" * 70)
    print()

    # Simulate a strategy with positive returns and some volatility
    np.random.seed(42)
    n_days = 252  # 1 year of daily data
    
    # Strategy with 10% annual return, 15% volatility
    daily_mean = 0.10 / 252
    daily_vol = 0.15 / np.sqrt(252)
    returns = np.random.normal(daily_mean, daily_vol, n_days)
    
    # Build equity curve
    initial_capital = 100000.0
    equity = initial_capital * np.cumprod(1 + returns)
    
    # Compute metrics
    report = compute_performance_metrics(
        equity_curve=equity,
        initial_capital=initial_capital,
        periods_per_year=252,
        risk_free_rate=0.02,  # 2% risk-free rate
    )
    
    print("Strategy Performance (1 year simulation):")
    print(f"  Initial Capital:  ${initial_capital:,.0f}")
    print(f"  Final Value:      ${equity[-1]:,.0f}")
    print(f"  CAGR:             {report.cagr * 100:.2f}%")
    print(f"  Max Drawdown:     ${report.max_drawdown:,.0f}")
    print()
    print(f"  Sharpe Ratio:     {report.sharpe_ratio:.3f}")
    print(f"  Sortino Ratio:    {report.sortino_ratio:.3f}")
    print(f"  Prob. Sharpe:     {report.probabilistic_sharpe_ratio:.3f}")
    print(f"  Hit Ratio:        {report.hit_ratio:.3f}" if report.hit_ratio else "  Hit Ratio:        N/A")
    print()
    print(f"  Expected Shortfall (95%): {report.expected_shortfall:.6f}")
    print(f"  Certainty Equivalent:     {report.certainty_equivalent * 100:.2f}%" if report.certainty_equivalent else "  Certainty Equivalent:     N/A")

    print("\n💡 Interpretation:")
    print("  Sharpe > 1.0: Good risk-adjusted returns")
    print("  Sortino > Sharpe: Upside volatility dominates (good)")
    print("  PSR > 0.95: High confidence the Sharpe is positive")
    print()


def example_var_es_and_kelly():
    """Demonstrate VaR/ES risk metrics and Kelly sizing."""
    print("=" * 70)
    print("Example 6: Risk Management (VaR, ES, Kelly)")
    print("=" * 70)
    print()

    # Simulate return distribution
    np.random.seed(42)
    returns = np.random.normal(0.001, 0.02, 1000)  # 0.1% mean, 2% vol
    
    # Compute VaR and ES
    var_95, es_95 = var_es(returns, alpha=0.975)
    var_99, es_99 = var_es(returns, alpha=0.99)
    
    print("Risk Metrics (on simulated returns):")
    print(f"  VaR (97.5%):  {var_95:.4f} (95% of losses are below this)")
    print(f"  ES (97.5%):   {es_95:.4f} (expected loss beyond VaR)")
    print()
    print(f"  VaR (99%):    {var_99:.4f}")
    print(f"  ES (99%):     {es_99:.4f}")
    print()
    
    # Kelly criterion with regime shrinkage
    mu = np.mean(returns)
    sigma2 = np.var(returns)
    
    print("Kelly Position Sizing:")
    print(f"  Expected Return:  {mu:.4f}")
    print(f"  Variance:         {sigma2:.6f}")
    print()
    
    for regime in ["EMERGENT", "CAUTION", "KILL"]:
        kelly_f = kelly_shrink(mu, sigma2, regime, f_max=1.0)
        print(f"  {regime:10s} regime: f = {kelly_f:.3f} ({kelly_f*100:.1f}% of capital)")
    
    print("\n💡 Trading Application:")
    print("  ES > threshold: Reduce position sizes or hedge")
    print("  KILL regime (f=0): No trading in high-risk periods")
    print("  CAUTION (f=0.5*Kelly): Half-Kelly for safer sizing")
    print("  EMERGENT (f=Kelly): Full Kelly when conditions are favorable")
    print()


def main():
    """Run all examples."""
    print("\n")
    print("╔" + "═" * 68 + "╗")
    print("║" + " " * 16 + "TradePulse Mathematical Metrics Examples" + " " * 12 + "║")
    print("╚" + "═" * 68 + "╝")
    print()
    
    try:
        example_dfa_analysis()
        example_aperiodic_slope()
        example_holder_exponent()
        example_edge_of_instability()
        example_performance_metrics()
        example_var_es_and_kelly()
        
        print("=" * 70)
        print("✅ All examples completed successfully!")
        print("=" * 70)
        print()
        print("📚 For more information, see:")
        print("   - docs/MATH_OVERVIEW.md - Complete mathematical reference")
        print("   - reports/MATH_VALIDATION_REPORT.md - Validation findings")
        print("   - docs/spec_fhmc.md - FHMC formal specification")
        print()
        
    except Exception as e:
        print(f"\n❌ Error running examples: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())
