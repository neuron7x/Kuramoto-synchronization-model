"""Energy monotonicity tests for damped wave solver."""

import numpy as np
import pytest
from src.tradepulse_qlw.pde_solver import NewmarkWaveSolver


def test_energy_decay_long():
    """Test that energy decreases monotonically in damped system."""
    s = NewmarkWaveSolver(
        nx=128,
        nt=2048,  # Reduced for faster testing
        dx=1.0,
        dt=0.02,
        c=2.0,
        gamma=0.2,
        noise_sigma=0.0,
        seed=7,
        pml_gain=0.0,
    )
    psi = s.solve()
    v = np.diff(psi, axis=0) / s.dt
    lap = np.zeros_like(psi)
    lap[:, 1:-1] = (psi[:, 2:] - 2 * psi[:, 1:-1] + psi[:, :-2]) / (s.dx * s.dx)
    # Align arrays: v is (nt-1, nx), lap and psi are (nt, nx)
    # Use first nt-1 timesteps for lap and psi to match v
    E = np.sum(v**2 + s.c**2 * lap[:-1] ** 2 + s.gamma * psi[:-1] ** 2, axis=1)
    # Allow small numerical tolerance
    assert np.all(np.diff(E) <= 1e-6), "Energy should be monotonically decreasing"


def test_energy_decay_medium():
    """Test energy decay with medium-length simulation."""
    s = NewmarkWaveSolver(
        nx=64,
        nt=1024,
        dx=1.0,
        dt=0.01,
        c=1.5,
        gamma=0.3,
        noise_sigma=0.0,
        seed=42,
        pml_gain=0.0,
    )
    x = np.arange(s.nx)
    u0 = np.exp(-0.01 * (x - s.nx // 2) ** 2)
    psi = s.solve(u0=u0)

    # Check that energy decreases overall
    initial_energy = np.sum(psi[0] ** 2)
    final_energy = np.sum(psi[-1] ** 2)
    assert final_energy < initial_energy, "Final energy should be less than initial"


def test_pml_reduces_reflection():
    """Test that PML reduces edge reflection."""
    # Without PML
    s1 = NewmarkWaveSolver(
        nx=128, nt=512, dx=1.0, dt=0.02, c=2.0, gamma=0.1, pml_gain=0.0, seed=42
    )
    x = np.arange(s1.nx)
    u0 = np.exp(-0.01 * (x - s1.nx // 2) ** 2)
    psi1 = s1.solve(u0=u0)

    # With PML
    s2 = NewmarkWaveSolver(
        nx=128, nt=512, dx=1.0, dt=0.02, c=2.0, gamma=0.1, pml_gain=2.0, seed=42
    )
    psi2 = s2.solve(u0=u0)

    # Measure edge energy
    edge_w = int(128 * 0.05)
    edge1 = np.sum(psi1[:, :edge_w] ** 2) + np.sum(psi1[:, -edge_w:] ** 2)
    edge2 = np.sum(psi2[:, :edge_w] ** 2) + np.sum(psi2[:, -edge_w:] ** 2)

    assert edge2 < edge1, "PML should reduce edge energy"
