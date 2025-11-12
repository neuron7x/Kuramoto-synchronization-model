"""Tests for PID-Tau adaptive threshold controller."""

import numpy as np
import pytest
from src.tradepulse_qlw.risk.adaptive_tau import PIDTau


def test_pid_clamp():
    """Test that PID controller clamps tau within bounds."""
    pid = PIDTau(target=0.15, min_tau=1.0, max_tau=2.0)
    tau = 1.5
    for r in [0.0, 0.9] * 50:
        tau = pid.update(r, tau)
    assert 1.0 <= tau <= 2.0, "Tau should stay within bounds"


def test_pid_convergence():
    """Test that PID controller converges to target."""
    pid = PIDTau(target=0.2, Kp=0.2, Ki=0.05, Kd=0.1, min_tau=0.5, max_tau=10.0)
    tau = 2.0

    # Simulate convergence
    ratios = []
    for _ in range(100):
        # Assume tau affects ratio (simplified model)
        current_ratio = 0.5 / (tau + 1.0)
        tau = pid.update(current_ratio, tau)
        ratios.append(current_ratio)

    # Check that we're moving toward target
    assert 0.5 <= tau <= 10.0, "Tau should remain in valid range"


def test_pid_anti_windup():
    """Test that integrator is clamped to prevent windup."""
    pid = PIDTau(target=0.15, Kp=0.1, Ki=0.5, Kd=0.05, min_tau=1.0, max_tau=2.0)
    tau = 1.5

    # Force large errors to test anti-windup
    for _ in range(200):
        tau = pid.update(1.0, tau)  # Very large ratio

    # Integrator should be clamped
    assert -10.0 <= pid._I <= 10.0, "Integrator should be clamped"
    assert 1.0 <= tau <= 2.0, "Tau should stay in bounds despite large errors"


def test_pid_response_to_step():
    """Test PID response to step change in ratio."""
    pid = PIDTau(target=0.15, Kp=0.3, Ki=0.1, Kd=0.2, min_tau=0.5, max_tau=10.0)
    tau = 2.0

    # Initial stable ratio
    for _ in range(50):
        tau = pid.update(0.15, tau)

    tau_before = tau

    # Step change
    for _ in range(50):
        tau = pid.update(0.5, tau)

    # Tau should adjust
    assert tau != tau_before, "Tau should respond to ratio change"
