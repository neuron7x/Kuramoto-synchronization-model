# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Ricci-flow + Kuramoto hybrid dynamics — executable falsification facade.

Thin, deterministic facade over the verified GeoSync engines. It does NOT
reimplement physics: trajectory hashing reuses
:func:`core.physics.determinism_kit.trajectory_hash`, and the order-parameter
and Kuramoto-step semantics mirror ``core/kuramoto`` (INV-K1). The flow here is a
heat-equation contraction on curvature dispersion whose Lyapunov energy is
provably non-increasing — a clean, self-contained witness target for the
``ricci_energy_nonincrease`` law.

All functions fail closed on contract violations (no silent repair).
"""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike, NDArray

from core.physics.determinism_kit import trajectory_hash as _trajectory_hash

__all__ = [
    "compute_order_parameter",
    "kuramoto_step",
    "ricci_energy",
    "ricci_flow_step",
    "hybrid_step",
    "trajectory_hash",
]


def _as_1d_finite(name: str, values: ArrayLike) -> NDArray[np.float64]:
    array = np.asarray(values, dtype=np.float64)
    if array.ndim != 1:
        raise ValueError(f"{name} must be 1-D, got ndim={array.ndim}; fail-closed")
    if array.size == 0:
        raise ValueError(f"{name} is empty; fail-closed")
    if not np.all(np.isfinite(array)):
        raise ValueError(f"{name} contains NaN/Inf; fail-closed")
    return array


def compute_order_parameter(phases: ArrayLike) -> float:
    """Mean-field Kuramoto order parameter R = |mean(exp(i*theta))| in [0, 1].

    INV-K1: R is a modulus of a convex combination of unit vectors, hence always
    within the unit interval by construction.
    """
    theta = _as_1d_finite("phases", phases)
    z = np.exp(1j * theta).mean()
    return float(np.abs(z))


def kuramoto_step(
    phases: ArrayLike,
    coupling: float,
    dt: float,
) -> NDArray[np.float64]:
    """One explicit mean-field Kuramoto step with zero natural frequencies.

    dtheta_i = dt * (K/N) * sum_j sin(theta_j - theta_i). Returns new phases.
    Fails closed on non-finite/non-positive dt or non-finite coupling.
    """
    theta = _as_1d_finite("phases", phases)
    if not np.isfinite(coupling):
        raise ValueError("coupling must be finite; fail-closed")
    if not np.isfinite(dt) or dt <= 0.0:
        raise ValueError(f"dt must be finite and > 0, got {dt!r}; fail-closed")
    n = theta.size
    diffs = theta[np.newaxis, :] - theta[:, np.newaxis]
    drift = (coupling / n) * np.sin(diffs).sum(axis=1)
    return theta + dt * drift


def ricci_energy(curvatures: ArrayLike) -> float:
    """Curvature-dispersion energy E(c) = sum_i (c_i - mean(c))^2 (>= 0).

    A Lyapunov functional for the smoothing flow in :func:`ricci_flow_step`.
    """
    curv = _as_1d_finite("curvatures", curvatures)
    centred = curv - curv.mean()
    return float(np.dot(centred, centred))


def ricci_flow_step(
    curvatures: ArrayLike,
    dt: float,
) -> NDArray[np.float64]:
    """Heat-equation contraction of curvature toward its mean.

    c_{t+1} = c_t - dt * (c_t - mean(c_t)). For dt in (0, 1] this is a strict
    contraction of the dispersion energy E (the (1-dt) factor squares to
    <= 1), so E never increases — the witnessed invariant.
    """
    curv = _as_1d_finite("curvatures", curvatures)
    if not np.isfinite(dt) or not (0.0 < dt <= 1.0):
        raise ValueError(f"dt must be in (0, 1], got {dt!r}; fail-closed")
    return curv - dt * (curv - curv.mean())


def hybrid_step(
    state: dict[str, ArrayLike],
    dt: float,
    causal_mask: ArrayLike,
) -> dict[str, NDArray[np.float64]]:
    """Advance phases and curvatures one step under a causal admissibility mask.

    ``state`` must carry ``phases`` (1-D), ``curvatures`` (1-D) and scalar
    ``coupling``. ``causal_mask`` is a boolean vector, one flag per oscillator,
    that gates which oscillators are allowed to couple this tick: a ``True``
    entry admits the oscillator, ``False`` freezes it. The mask must be boolean,
    1-D and length-matched to ``phases`` — anything else (including a mask that
    is not strictly past-admissible, i.e. all-False) fails closed, which is the
    hook the negative control exploits to inject an invalid "future" mask.
    """
    if "phases" not in state or "curvatures" not in state or "coupling" not in state:
        raise ValueError("state must contain 'phases', 'curvatures', 'coupling'; fail-closed")
    phases = _as_1d_finite("phases", state["phases"])
    curvatures = _as_1d_finite("curvatures", state["curvatures"])
    coupling_arr = np.asarray(state["coupling"], dtype=np.float64)
    if coupling_arr.ndim != 0:
        raise ValueError("state['coupling'] must be a scalar; fail-closed")
    coupling = float(coupling_arr)

    mask = np.asarray(causal_mask)
    if mask.dtype != np.bool_:
        raise ValueError(f"causal_mask must be boolean, got dtype={mask.dtype}; fail-closed")
    if mask.shape != phases.shape:
        raise ValueError(
            f"causal_mask shape {mask.shape} must match phases shape {phases.shape}; fail-closed"
        )
    if not bool(mask.any()):
        raise ValueError("causal_mask admits no oscillator (all-False); fail-closed")

    gated_coupling = coupling if bool(mask.all()) else coupling * float(mask.mean())
    new_phases = kuramoto_step(phases, gated_coupling, dt)
    new_curvatures = ricci_flow_step(curvatures, dt)
    return {"phases": new_phases, "curvatures": new_curvatures}


def trajectory_hash(trajectory: ArrayLike) -> str:
    """Deterministic hash of a trajectory, delegating to the reproducibility kit.

    Reuses :func:`core.physics.determinism_kit.trajectory_hash` (INV-DET1/2) so
    the hash is ULP-sensitive and order-aware. Coerces list input to a 2-D float
    array first; fails closed on non-finite content.
    """
    array = np.asarray(trajectory, dtype=np.float64)
    if array.ndim != 2:
        raise ValueError(f"trajectory must be 2-D (steps, dims), got ndim={array.ndim}")
    if not np.all(np.isfinite(array)):
        raise ValueError("trajectory contains NaN/Inf; fail-closed")
    return _trajectory_hash(array)
