# SPDX-License-Identifier: MIT
"""LAW T7 — Operational pinning control of deterministic chaos.

Constitutional Law T7 of seven (CLAUDE.md GeoSync Physics Law Act).
Self-contained physics-based controller; NO external models, NO ML.

Identity
--------
Wang & Chen (2002) "Pinning control of complex networks": for a
diffusive-coupled network with graph Laplacian ``L``, choose a
*pinned subset* ``P ⊂ V`` and apply uniform-gain feedback only to
those nodes,

    u_i(t)  =  −γ · (x_i(t) − x_target_i)   for i ∈ P,
    u_i(t)  =  0                             otherwise,

The closed-loop dynamics ``ẋ = f(x) − L·x − Γ_P·(x − x_target)``
synchronises to the target iff the algebraic connectivity of the
augmented Laplacian is positive:

    λ_2(L + Γ_P)  >  ε_pin.                          (gain margin)

The pinned set ``P`` is selected GREEDILY to maximise ``λ_2(L + Γ_P)``
in O(N²·k) time. No black-box; no learned model. The selection is
deterministic for a given ``(A, gain, k_min, ε_pin)``.

Constitutional invariants (P0)
------------------------------
* INV-PIN1 | universal | for the returned ``P``:
                          ``λ_2(L + Γ_P) > ε_pin`` OR ``len(P) =
                          k_min`` AND status == INSUFFICIENT.
                          Fail-closed: never silently report "control
                          on" when the gain margin is non-positive.
* INV-PIN2 | conditional | pinning step is contractive in the
                          linearised regime: a single pinning_step
                          with x_target = 0 reduces ``‖x‖²`` whenever
                          ``λ_2(L + Γ_P) > 0`` and ``dt`` is below
                          the stability bound ``2 / λ_max(L + Γ_P)``.
* INV-PIN3 | universal | pinning never increases the connectivity of
                          the unpinned subgraph: edges outside ``P``
                          are not modified. Topology preservation.
* INV-PIN4 | universal | every contract violation (signed adjacency,
                          gain ≤ 0, ε_pin < 0, k_min > N, dt ≤ 0,
                          shape mismatch) raises ValueError;
                          fail-closed.

Determinism: pure functions; identical inputs ⇒ identical outputs
to float precision (INV-HPC1 compat).

References
----------
* Wang, X. F.; Chen, G. (2002). *Pinning control of scale-free
  dynamical networks.* Physica A 310, 521–531.
* Sorrentino, F. et al. (2007). *Controllability of complex
  networks via pinning.* Phys. Rev. E 75, 046103.
* Olfati-Saber, R.; Murray, R. M. (2004). *Consensus problems in
  networks of agents with switching topology and time-delays.*
  IEEE Trans. Autom. Control 49, 1520–1533.
"""

from __future__ import annotations

from enum import Enum
from typing import NamedTuple

import numpy as np
from numpy.typing import NDArray

__all__ = [
    "PinningReport",
    "PinningStatus",
    "algebraic_connectivity",
    "graph_laplacian",
    "pinning_gain_margin",
    "pinning_step",
    "select_pinning_set",
]


class PinningStatus(str, Enum):
    """Outcome class for ``select_pinning_set``."""

    SUFFICIENT = "SUFFICIENT"
    INSUFFICIENT = "INSUFFICIENT"


class PinningReport(NamedTuple):
    """Outcome of one ``select_pinning_set`` invocation.

    Attributes
    ----------
    status:
        SUFFICIENT iff the returned set achieves ``λ_2(L + Γ_P) >
        ε_pin``; otherwise INSUFFICIENT (gain too small or topology
        too sparse).
    pinned_indices:
        Sorted tuple of node indices in ``P``.
    gain_margin:
        ``λ_2(L + Γ_P)`` at the returned ``P``.
    iterations:
        Number of nodes added (``= len(P)``).
    """

    status: PinningStatus
    pinned_indices: tuple[int, ...]
    gain_margin: float
    iterations: int


# ── Spectral primitives ──────────────────────────────────────────────────────


def graph_laplacian(A: NDArray[np.floating]) -> NDArray[np.floating]:
    """Combinatorial Laplacian ``L = D − A`` for symmetric, non-negative ``A``.

    Diagonal of ``A`` is treated as zero (self-loops ignored). Returns
    a fresh contiguous array with the same dtype as ``A``.
    """
    if A.ndim != 2 or A.shape[0] != A.shape[1]:
        raise ValueError(f"INV-PIN4: A must be square 2-D, got shape {A.shape}")
    if not np.all(A >= 0.0):
        raise ValueError("INV-PIN4: A must have non-negative entries.")
    A_no_diag = A.copy()
    np.fill_diagonal(A_no_diag, 0.0)
    A_sym = 0.5 * (A_no_diag + A_no_diag.T)
    D = np.diag(np.sum(A_sym, axis=1))
    return np.asarray(D - A_sym, dtype=A.dtype)


def algebraic_connectivity(A: NDArray[np.floating]) -> float:
    """Fiedler eigenvalue λ_2(L) of the (symmetric) Laplacian (INV-SG1/SG2).

    Returns 0.0 for disconnected graphs. Returns the second-smallest
    eigenvalue for connected ones.
    """
    L = graph_laplacian(A)
    eigs = np.linalg.eigvalsh(L)
    # eigvalsh sorts ascending; eigs[0] ≈ 0 (constant mode); eigs[1] = λ_2.
    return float(eigs[1])


def pinning_gain_margin(
    A: NDArray[np.floating],
    pinned_indices: tuple[int, ...] | list[int] | set[int],
    gain: float,
) -> float:
    """λ_2(L + Γ_P) for a given pinned set and uniform gain.

    The diagonal pinning matrix ``Γ_P`` is ``γ`` on rows in ``P``,
    zero elsewhere. ``λ_2`` of ``L + Γ_P`` is the gain margin used
    by INV-PIN1.
    """
    if gain <= 0.0:
        raise ValueError(f"INV-PIN4: gain must be > 0, got {gain}")
    n: int = int(A.shape[0])
    P_set = set(int(i) for i in pinned_indices)
    if any(i < 0 or i >= n for i in P_set):
        raise ValueError(f"INV-PIN4: pinned_indices contain out-of-range nodes for N={n}")
    L = graph_laplacian(A)
    Gamma = np.zeros((n, n), dtype=L.dtype)
    for i in P_set:
        Gamma[i, i] = gain
    eigs = np.linalg.eigvalsh(L + Gamma)
    return float(eigs[1] if n >= 2 else eigs[0])


# ── Pinning-set selection (greedy) ───────────────────────────────────────────


def select_pinning_set(
    A: NDArray[np.floating],
    *,
    gain: float,
    eps_pin: float = 1e-3,
    k_max: int | None = None,
) -> PinningReport:
    """Greedy O(N²·k) selection of ``P`` maximising ``λ_2(L + Γ_P)``.

    At each iteration, pick the node that maximises the augmented
    Fiedler eigenvalue. Stop when either (a) λ_2 > eps_pin
    (status SUFFICIENT), or (b) ``k_max`` nodes are pinned (status
    INSUFFICIENT if the threshold was not met).

    Parameters
    ----------
    A:
        Symmetric, non-negative-entry adjacency, shape (N, N).
    gain:
        Uniform pinning gain γ. Must be > 0.
    eps_pin:
        Minimum acceptable gain margin λ_2(L + Γ_P). Default 1e-3.
    k_max:
        Maximum number of pinned nodes. Defaults to ``N`` (all).

    Raises
    ------
    ValueError
        On any contract violation. Fail-closed (INV-PIN4).
    """
    if A.ndim != 2 or A.shape[0] != A.shape[1]:
        raise ValueError(f"INV-PIN4: A must be square 2-D, got shape {A.shape}")
    if not np.all(A >= 0.0):
        raise ValueError("INV-PIN4: A must have non-negative entries.")
    if gain <= 0.0:
        raise ValueError(f"INV-PIN4: gain must be > 0, got {gain}")
    if eps_pin < 0.0:
        raise ValueError(f"INV-PIN4: eps_pin must be ≥ 0, got {eps_pin}")
    n: int = int(A.shape[0])
    if k_max is None:
        k_max_eff = n
    else:
        if k_max <= 0 or k_max > n:
            raise ValueError(f"INV-PIN4: k_max must satisfy 1 ≤ k_max ≤ {n}, got {k_max}")
        k_max_eff = int(k_max)

    L = graph_laplacian(A)
    P: list[int] = []
    last_lambda: float = float(np.linalg.eigvalsh(L)[1] if n >= 2 else 0.0)

    for _ in range(k_max_eff):
        best_i: int = -1
        best_lambda: float = -np.inf
        for cand in range(n):
            if cand in P:
                continue
            Gamma = np.zeros((n, n), dtype=L.dtype)
            for i in P + [cand]:
                Gamma[i, i] = gain
            eigs = np.linalg.eigvalsh(L + Gamma)
            lam = float(eigs[1] if n >= 2 else eigs[0])
            if lam > best_lambda:
                best_lambda = lam
                best_i = cand
        if best_i < 0:
            break
        P.append(best_i)
        last_lambda = best_lambda
        if last_lambda > eps_pin:
            break

    P_sorted: tuple[int, ...] = tuple(sorted(P))
    status = PinningStatus.SUFFICIENT if last_lambda > eps_pin else PinningStatus.INSUFFICIENT
    return PinningReport(
        status=status,
        pinned_indices=P_sorted,
        gain_margin=last_lambda,
        iterations=len(P_sorted),
    )


# ── Pinning step (the control law itself) ────────────────────────────────────


def pinning_step(
    x: NDArray[np.floating],
    *,
    A: NDArray[np.floating],
    pinned_indices: tuple[int, ...] | list[int] | set[int],
    gain: float,
    target: NDArray[np.floating] | None = None,
    dt: float,
) -> NDArray[np.floating]:
    """One explicit-Euler step of the pinning-controlled diffusive flow.

    ``ẋ  =  −L · x  −  Γ_P · (x − x_target)``.

    Parameters
    ----------
    x:
        Current state, shape (N,).
    A:
        Adjacency, shape (N, N), symmetric, non-negative.
    pinned_indices:
        Indices of pinned nodes ``P``.
    gain:
        Uniform pinning gain γ > 0.
    target:
        Target state, shape (N,). Default zero.
    dt:
        Integration timestep. Must be > 0 and below
        ``2 / λ_max(L + Γ_P)`` for stability (INV-PIN2).

    Returns
    -------
    NDArray
        Next state, shape (N,).

    Raises
    ------
    ValueError
        On any contract violation. Fail-closed (INV-PIN4).
    """
    if x.ndim != 1:
        raise ValueError(f"INV-PIN4: x must be 1-D, got shape {x.shape}")
    if A.shape[0] != x.shape[0] or A.shape[0] != A.shape[1]:
        raise ValueError(f"INV-PIN4: shape mismatch: A {A.shape} vs x {x.shape}")
    if gain <= 0.0:
        raise ValueError(f"INV-PIN4: gain must be > 0, got {gain}")
    if dt <= 0.0:
        raise ValueError(f"INV-PIN4: dt must be > 0, got {dt}")
    n: int = int(x.shape[0])
    target_eff = np.zeros(n, dtype=x.dtype) if target is None else target
    if target_eff.shape != x.shape:
        raise ValueError(f"INV-PIN4: target shape {target_eff.shape} ≠ x shape {x.shape}")

    L = graph_laplacian(A)
    P_set = set(int(i) for i in pinned_indices)
    if any(i < 0 or i >= n for i in P_set):
        raise ValueError(f"INV-PIN4: pinned_indices out-of-range for N={n}")
    pin_mask = np.zeros(n, dtype=x.dtype)
    for i in P_set:
        pin_mask[i] = gain
    dx = -L @ x - pin_mask * (x - target_eff)
    return np.asarray(x + dt * dx, dtype=x.dtype)
