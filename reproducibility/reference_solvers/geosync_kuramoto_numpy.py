# SPDX-License-Identifier: MIT
"""Pure NumPy reference solver for the GeoSync weighted Kuramoto lane.

This module intentionally avoids JAX and production runtime helpers. It is a
small independent implementation used only for replication tests.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]


def kuramoto_numpy_rhs(
    theta: FloatArray,
    omega: FloatArray,
    adjacency: FloatArray,
) -> FloatArray:
    """Return dtheta/dt for weighted graph Kuramoto dynamics."""
    delta = theta[None, :] - theta[:, None]
    coupling = np.sum(adjacency * np.sin(delta), axis=1)
    return omega + coupling


def kuramoto_numpy_step(
    theta: FloatArray,
    *,
    dt: float,
    omega: FloatArray,
    adjacency: FloatArray,
) -> FloatArray:
    """Single midpoint/RK2 step matching the production integration contract."""
    f1 = kuramoto_numpy_rhs(theta, omega, adjacency)
    midpoint = theta + 0.5 * dt * f1
    f2 = kuramoto_numpy_rhs(midpoint, omega, adjacency)
    return theta + dt * f2


def kuramoto_numpy_trajectory(
    theta_0: FloatArray,
    *,
    dt: float,
    n_steps: int,
    omega: FloatArray,
    adjacency: FloatArray,
) -> FloatArray:
    """Integrate a deterministic NumPy trajectory with shape (n_steps + 1, N)."""
    if dt <= 0.0:
        raise ValueError(f"dt must be positive, got {dt}")
    if n_steps <= 0:
        raise ValueError(f"n_steps must be positive, got {n_steps}")
    if theta_0.ndim != 1:
        raise ValueError(f"theta_0 must be 1-D, got shape {theta_0.shape}")
    if adjacency.ndim != 2 or adjacency.shape[0] != adjacency.shape[1]:
        raise ValueError(f"adjacency must be square, got shape {adjacency.shape}")
    if adjacency.shape[0] != theta_0.shape[0] or omega.shape != theta_0.shape:
        raise ValueError("theta_0, omega, and adjacency dimensions must agree")

    trajectory = np.zeros((n_steps + 1, theta_0.shape[0]), dtype=np.float64)
    theta = theta_0.astype(np.float64, copy=True)
    trajectory[0] = theta
    for step in range(n_steps):
        theta = kuramoto_numpy_step(
            theta,
            dt=dt,
            omega=omega,
            adjacency=adjacency,
        )
        trajectory[step + 1] = theta
    return trajectory


def order_parameter_numpy(theta: FloatArray) -> FloatArray:
    """Return Kuramoto order parameter for one state or a trajectory."""
    return np.abs(np.mean(np.exp(1j * theta), axis=-1))
