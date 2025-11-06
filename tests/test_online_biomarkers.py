"""Tests for online biomarker monitoring enhancements."""
import numpy as np
import pytest

from core.metrics.online_biomarkers import (
    BiomarkerState,
    OnlineBiomarkerMonitor,
)


def test_online_monitor_initialization():
    """Test OnlineBiomarkerMonitor initialization."""
    monitor = OnlineBiomarkerMonitor(
        window_size=1000,
        alpha_target=(0.8, 1.0),
    )
    assert monitor.window_size == 1000
    assert monitor.alpha_target == (0.8, 1.0)
    assert len(monitor._buffer) == 0


def test_online_monitor_update():
    """Test buffer updates."""
    monitor = OnlineBiomarkerMonitor(window_size=100)
    
    for i in range(150):
        monitor.update(float(i))
    
    # Buffer should be limited to window_size
    assert len(monitor._buffer) == 100
    assert monitor._buffer[-1] == 149.0


def test_alpha_computation_insufficient_data():
    """Test alpha computation with insufficient data."""
    monitor = OnlineBiomarkerMonitor(window_size=1000, min_win=50)
    
    # Add only 20 samples
    for i in range(20):
        monitor.update(float(i))
    
    alpha = monitor.compute_alpha()
    assert alpha is None


def test_alpha_computation_sufficient_data():
    """Test alpha computation with sufficient data."""
    monitor = OnlineBiomarkerMonitor(window_size=2000, min_win=50)
    
    # Generate pink noise-like data
    np.random.seed(42)
    data = np.cumsum(np.random.randn(500))
    
    for val in data:
        monitor.update(float(val))
    
    alpha = monitor.compute_alpha()
    assert alpha is not None
    assert 0.0 <= alpha <= 1.5


def test_holder_exponent_computation():
    """Test Hölder exponent computation."""
    monitor = OnlineBiomarkerMonitor()
    
    # Generate series with known structure
    series = np.cumsum(np.random.randn(100))
    holder = monitor.compute_holder_exponent(series)
    
    assert 0.0 <= holder <= 1.0


def test_white_noise_detection():
    """Test white noise detection fallback."""
    monitor = OnlineBiomarkerMonitor()
    
    # Alpha close to 0.5 should be detected as white noise
    assert monitor.detect_white_noise(0.51)
    assert monitor.detect_white_noise(0.49)
    
    # Alpha away from 0.5 should not be white noise
    assert not monitor.detect_white_noise(0.8)
    assert not monitor.detect_white_noise(0.3)


def test_target_range_check():
    """Test alpha target range validation."""
    monitor = OnlineBiomarkerMonitor(alpha_target=(0.8, 1.0))
    
    assert monitor.is_in_target_range(0.85)
    assert monitor.is_in_target_range(0.8)
    assert monitor.is_in_target_range(1.0)
    assert not monitor.is_in_target_range(0.7)
    assert not monitor.is_in_target_range(1.1)


def test_biomarker_state():
    """Test biomarker state retrieval."""
    monitor = OnlineBiomarkerMonitor(alpha_target=(0.8, 1.0))
    
    # Generate data
    np.random.seed(42)
    data = np.cumsum(np.random.randn(500))
    for val in data:
        monitor.update(float(val))
    
    # Compute some alphas
    for _ in range(5):
        alpha = monitor.compute_alpha()
        if alpha is not None:
            monitor._alpha_history.append(alpha)
    
    state = monitor.get_state()
    
    assert isinstance(state, BiomarkerState)
    assert 0.0 <= state.alpha <= 1.5
    assert state.alpha_target_low == 0.8
    assert state.alpha_target_high == 1.0
    assert 0.0 <= state.retention_metric <= 2.0


def test_retention_metric_stability():
    """Test retention metric measures stability."""
    monitor = OnlineBiomarkerMonitor()
    
    # Stable alphas
    monitor._alpha_history = [0.85, 0.86, 0.85, 0.84, 0.86, 0.85, 0.85, 0.86, 0.85, 0.85]
    state = monitor.get_state()
    
    # Should have high retention (low variation)
    assert state.retention_metric > 0.9


def test_backward_transfer_improvement():
    """Test backward transfer captures improvement."""
    monitor = OnlineBiomarkerMonitor()
    
    # Improving alphas over time
    monitor._alpha_history = [0.7, 0.75, 0.8, 0.85, 0.9]
    state = monitor.get_state()
    
    # Backward transfer should be positive
    assert state.backward_transfer > 0


def test_convergence_rate():
    """Test convergence rate toward target."""
    monitor = OnlineBiomarkerMonitor(alpha_target=(0.8, 1.0))
    
    # Alphas converging to target center (0.9)
    monitor._alpha_history = [0.6, 0.7, 0.75, 0.82, 0.88]
    state = monitor.get_state()
    
    # Convergence rate should be positive (distance decreasing)
    assert state.convergence_rate > 0
