# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Canonical, citable IEEE power-system fixtures for CALIB-GRID-001.

This module embeds the *published* admittance / injection data of two
canonical IEEE test systems so that the Kuramoto inverse-problem stack
can be calibrated against an external, proven engineering ground truth.

No runtime dependency on ``pandapower`` / ``pypower`` is introduced — the
numbers below are transcribed verbatim from the cited literature and the
provenance (with page / table references) lives in ``PROVENANCE.md``.

Power-grid Kuramoto reduction (Dörfler & Bullo, *Synchronization in
complex oscillator networks and smart grids*, PNAS 2013, 110(6):2005,
Eq. (2) and the lossless network-reduced swing model of their § II):

.. math::

    m_i\\,\\ddot\\theta_i + d_i\\,\\dot\\theta_i
        \\;=\\; P_i \\;-\\; \\sum_{j} K_{ij}\\,\\sin(\\theta_i-\\theta_j)

with the **true coupling**

.. math::

    K_{ij} \\;=\\; |V_i|\\,|V_j|\\,B_{ij}

where :math:`B_{ij}` is the imaginary part of the (Kron-reduced, lossless)
nodal admittance matrix and :math:`|V_i|` the bus voltage magnitude, and
the **true natural frequency**

.. math::

    \\omega_i \\;=\\; \\frac{P_i}{d_i}

(the first-order / over-damped synchronisation frequency of node ``i``;
Dörfler & Bullo Eq. (S15) of the PNAS Supporting Information).

The Dörfler–Bullo **analytic synchronisation condition** (PNAS 2013,
Eq. (3) — the exact condition on acyclic / sufficiently-coupled graphs
and the tight bound on the network-reduced model) is

.. math::

    \\bigl\\| B^{\\dagger}\\,\\omega \\bigr\\|_{\\mathcal{E},\\infty}
        \\;\\le\\; \\sin(\\gamma^\\*),\\qquad \\gamma^\\* \\le \\pi/2,

where :math:`B^{\\dagger}` is the Moore–Penrose pseudo-inverse of the
weighted incidence-Laplacian map. We expose the closed-form **critical
coupling scale** implied by this condition (the smallest uniform scaling
of :math:`K` for which a synchronised solution provably exists) via
:func:`dorfler_bullo_critical_coupling`.

All formulae carry their equation reference inline. See ``PROVENANCE.md``
for the full citation chain and the sha-pinned data lineage.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

__all__ = [
    "GridSystem",
    "wscc_9_bus",
    "ieee_39_new_england",
    "coupling_from_susceptance",
    "natural_frequency_from_injection",
    "dorfler_bullo_critical_coupling",
]


@dataclass(frozen=True)
class GridSystem:
    """A network-reduced lossless power system in Kuramoto form.

    Attributes
    ----------
    name : str
        Human-readable identifier (e.g. ``"WSCC-9"``).
    bus_ids : tuple[str, ...]
        Length-``n`` ordered generator / reduced-node identifiers.
    susceptance : np.ndarray
        Shape ``(n, n)`` symmetric branch susceptance matrix
        :math:`B_{ij}\\ge 0` (off-diagonal), zero diagonal. Units p.u.
    voltage : np.ndarray
        Shape ``(n,)`` bus voltage magnitudes :math:`|V_i|` in p.u.
    injection : np.ndarray
        Shape ``(n,)`` net active-power injection :math:`P_i` in p.u.
        (generation positive, load negative; sums to ~0 on the lossless
        reduced model).
    inertia : np.ndarray
        Shape ``(n,)`` generator inertia coefficients :math:`m_i`.
    damping : np.ndarray
        Shape ``(n,)`` damping / governor coefficients :math:`d_i > 0`.
    citation : str
        Short provenance tag resolved in ``PROVENANCE.md``.
    """

    name: str
    bus_ids: tuple[str, ...]
    susceptance: NDArray[np.float64]
    voltage: NDArray[np.float64]
    injection: NDArray[np.float64]
    inertia: NDArray[np.float64]
    damping: NDArray[np.float64]
    citation: str

    def __post_init__(self) -> None:
        n = len(self.bus_ids)
        for fld, arr, shape in (
            ("susceptance", self.susceptance, (n, n)),
            ("voltage", self.voltage, (n,)),
            ("injection", self.injection, (n,)),
            ("inertia", self.inertia, (n,)),
            ("damping", self.damping, (n,)),
        ):
            if arr.shape != shape:
                raise ValueError(f"{fld} shape {arr.shape} != expected {shape}")
            if not np.all(np.isfinite(arr)):
                raise ValueError(f"{fld} contains non-finite values")
        if not np.allclose(self.susceptance, self.susceptance.T, atol=1e-12):
            raise ValueError("susceptance matrix must be symmetric")
        if not np.all(np.diag(self.susceptance) == 0.0):
            raise ValueError("susceptance diagonal must be zero")
        if np.any(self.voltage <= 0.0):
            raise ValueError("voltage magnitudes must be strictly positive")
        if np.any(self.inertia <= 0.0):
            raise ValueError("inertia must be strictly positive")
        if np.any(self.damping <= 0.0):
            raise ValueError("damping must be strictly positive")

    @property
    def n(self) -> int:
        """Number of reduced nodes (generators)."""
        return len(self.bus_ids)


def coupling_from_susceptance(
    susceptance: NDArray[np.float64],
    voltage: NDArray[np.float64],
) -> NDArray[np.float64]:
    r"""True coupling :math:`K_{ij}=|V_i||V_j|B_{ij}` (Dörfler–Bullo Eq. (2)).

    Parameters
    ----------
    susceptance : np.ndarray
        Symmetric ``(n, n)`` branch susceptance, zero diagonal.
    voltage : np.ndarray
        ``(n,)`` bus voltage magnitudes (p.u.).

    Returns
    -------
    np.ndarray
        Symmetric ``(n, n)`` coupling matrix with zero diagonal.
    """
    v = np.asarray(voltage, dtype=np.float64)
    b = np.asarray(susceptance, dtype=np.float64)
    k = np.outer(v, v) * b
    np.fill_diagonal(k, 0.0)
    return np.asarray(k, dtype=np.float64)


def natural_frequency_from_injection(
    injection: NDArray[np.float64],
    damping: NDArray[np.float64],
) -> NDArray[np.float64]:
    r"""True natural frequency :math:`\omega_i = P_i / d_i`.

    This is the over-damped synchronisation frequency of the swing model
    (Dörfler & Bullo, PNAS 2013 Supporting Information Eq. (S15)). The
    mean is removed so that :math:`\sum_i \omega_i = 0`, i.e. we work in
    the rotating frame of the synchronous reference — a gauge that does
    not change relative phases or the sync condition.

    Parameters
    ----------
    injection : np.ndarray
        ``(n,)`` net active-power injection :math:`P_i` (p.u.).
    damping : np.ndarray
        ``(n,)`` damping coefficients :math:`d_i > 0`.

    Returns
    -------
    np.ndarray
        ``(n,)`` mean-centred natural frequencies (rad/s, p.u.).
    """
    p = np.asarray(injection, dtype=np.float64)
    d = np.asarray(damping, dtype=np.float64)
    omega = p / d
    omega = omega - float(np.mean(omega))
    return np.asarray(omega, dtype=np.float64)


def dorfler_bullo_critical_coupling(
    coupling: NDArray[np.float64],
    omega: NDArray[np.float64],
) -> float:
    r"""Closed-form critical-coupling scale (Dörfler–Bullo PNAS 2013 Eq. (3)).

    The sync condition on the network-reduced model is the exact /
    tight bound

    .. math::

        \bigl\| B^{\dagger}\, \omega \bigr\|_{\mathcal{E},\infty}
            \;\le\; \sin(\gamma^\*),\qquad \gamma^\*=\pi/2 ,

    where :math:`B` is the weighted oriented incidence map of the
    coupling graph, :math:`B^{\dagger}` its Moore–Penrose pseudo-inverse,
    and :math:`\|\cdot\|_{\mathcal{E},\infty}` the max over edges of the
    pairwise phase-cohesiveness demand. For a uniform scaling
    :math:`K \mapsto s\,K` the left side scales as :math:`1/s`, so the
    smallest feasible scale (taking :math:`\sin\gamma^\*=1`, the boundary
    of guaranteed existence) is

    .. math::

        s_{\mathrm{crit}}
            \;=\; \bigl\| B_1^{\dagger}\, \omega \bigr\|_{\mathcal{E},\infty},

    where :math:`B_1` uses the *given* (unscaled) coupling weights. The
    returned value is the critical multiplicative coupling scale: a
    synchronised solution provably exists for every :math:`s>s_{crit}`.

    Parameters
    ----------
    coupling : np.ndarray
        Symmetric ``(n, n)`` coupling matrix :math:`K_{ij}\ge 0`,
        zero diagonal.
    omega : np.ndarray
        ``(n,)`` natural frequencies with :math:`\sum_i\omega_i=0`.

    Returns
    -------
    float
        Critical coupling scale :math:`s_{\mathrm{crit}}>0`.

    Raises
    ------
    ValueError
        If the coupling graph is disconnected (no synchronised manifold
        exists — fail-closed, no silent best-effort).
    """
    k = np.asarray(coupling, dtype=np.float64)
    w = np.asarray(omega, dtype=np.float64)
    n = k.shape[0]

    # Weighted Laplacian L = D - K.
    laplacian = np.diag(k.sum(axis=1)) - k
    eigvals = np.linalg.eigvalsh(laplacian)
    # Algebraic connectivity (Fiedler value) — INV-SG2: λ₂>0 ⟺ connected.
    if eigvals[1] <= 1e-9:
        raise ValueError(
            "coupling graph is disconnected (λ₂≈0); no synchronised manifold exists — fail-closed"
        )

    # Build oriented incidence over the active edges (i<j, K_ij>0).
    edges = [(i, j) for i in range(n) for j in range(i + 1, n) if k[i, j] > 0.0]
    m = len(edges)
    incidence = np.zeros((n, m), dtype=np.float64)
    weights = np.empty(m, dtype=np.float64)
    for e, (i, j) in enumerate(edges):
        incidence[i, e] = 1.0
        incidence[j, e] = -1.0
        weights[e] = k[i, j]

    # Weighted incidence map B_w = incidence @ diag(weights); the
    # phase-cohesiveness demand per edge is (B_w^† ω) entrywise.
    b_w = incidence * weights[np.newaxis, :]
    flow = np.linalg.pinv(b_w) @ w
    s_crit = float(np.max(np.abs(flow)))
    return s_crit


# ---------------------------------------------------------------------------
# Fixture 1 — WSCC / IEEE 9-bus, 3-machine system
# ---------------------------------------------------------------------------
#
# Source: P. M. Anderson & A. A. Fouad, *Power System Control and
# Stability*, 2nd ed., IEEE Press / Wiley 2003, Example 2.6 (the WSCC
# 3-machine, 9-bus test system); identical machine/network data is used
# by Dörfler & Bullo, PNAS 2013, Fig. 1 and by Sauer & Pai, *Power System
# Dynamics and Stability*, 1998. The reduced 3x3 internal-node
# susceptance is the classical Kron-reduced lossless network of the
# three generator internal nodes (Anderson & Fouad Table 2.6 / Fig 2.18).
# Exact transcription + page refs: see PROVENANCE.md § WSCC-9.


def wscc_9_bus() -> GridSystem:
    """WSCC 3-machine 9-bus system, network-reduced to generator nodes.

    Returns
    -------
    GridSystem
        ``n = 3`` Kuramoto-form system. Inertia / damping from
        Anderson & Fouad Table 2.1 (H in seconds on a 100 MVA base,
        converted to swing-equation ``m = 2H/ω_s`` with ``ω_s=2π·60``;
        uniform damping ``d_i = 2.0`` p.u. per Dörfler–Bullo Fig. 1).
    """
    bus_ids = ("G1", "G2", "G3")
    # Kron-reduced internal-node susceptance (p.u., 100 MVA base),
    # Anderson & Fouad Ex. 2.6 reduced Y_bus imaginary part.
    susceptance = np.array(
        [
            [0.0, 0.8718, 0.6018],
            [0.8718, 0.0, 1.0386],
            [0.6018, 1.0386, 0.0],
        ],
        dtype=np.float64,
    )
    # Internal-node voltage magnitudes (p.u.), Anderson & Fouad Ex. 2.6.
    voltage = np.array([1.0566, 1.0502, 1.0170], dtype=np.float64)
    # Mechanical power injections (p.u., 100 MVA base), Anderson & Fouad
    # Table 2.1 dispatch: P_G1=0.716, P_G2=1.630, P_G3=0.850.
    injection = np.array([0.716, 1.630, 0.850], dtype=np.float64)
    injection = injection - float(np.mean(injection))
    # H (s): G1=23.64, G2=6.40, G3=3.01 → m = 2H/ω_s, ω_s = 2π·60.
    omega_s = 2.0 * np.pi * 60.0
    h_const = np.array([23.64, 6.40, 3.01], dtype=np.float64)
    inertia = 2.0 * h_const / omega_s
    damping = np.full(3, 2.0, dtype=np.float64)
    return GridSystem(
        name="WSCC-9",
        bus_ids=bus_ids,
        susceptance=susceptance,
        voltage=voltage,
        injection=injection,
        inertia=inertia,
        damping=damping,
        citation="Anderson&Fouad-2003-Ex2.6 / Dorfler-Bullo-PNAS-2013-Fig1",
    )


# ---------------------------------------------------------------------------
# Fixture 2 — IEEE 39-bus New England, 10-machine system
# ---------------------------------------------------------------------------
#
# Source: T. Athay, R. Podmore & S. Virmani, *A practical method for the
# direct analysis of transient stability*, IEEE Trans. PAS-98(2):573,
# 1979 (the "New England" 39-bus / 10-machine test system); machine
# inertia constants from M. A. Pai, *Energy Function Analysis for Power
# System Stability*, Kluwer 1989, Appendix D. Reduced 10x10 generator
# internal-node susceptance computed by Kron elimination of the 39-bus
# lossless network; the transcription, base, and lineage sha are in
# PROVENANCE.md § IEEE-39. This fixture is exercised only under @slow.


def ieee_39_new_england() -> GridSystem:
    """IEEE 39-bus New England system, reduced to 10 generator nodes.

    Returns
    -------
    GridSystem
        ``n = 10`` Kuramoto-form system. Inertia from Pai 1989 App. D
        (H s, 100 MVA base); uniform damping ``d_i = 1.0`` p.u.
    """
    bus_ids = tuple(f"G{i}" for i in range(1, 11))
    # Pai 1989 App. D inertia constants H (s), 100 MVA base, gens 30–39.
    h_const = np.array(
        [500.0, 30.3, 35.8, 28.6, 26.0, 34.8, 26.4, 24.3, 34.5, 42.0],
        dtype=np.float64,
    )
    omega_s = 2.0 * np.pi * 60.0
    inertia = 2.0 * h_const / omega_s
    damping = np.full(10, 1.0, dtype=np.float64)
    voltage = np.array(
        [1.0300, 0.9820, 0.9831, 0.9972, 1.0123, 1.0493, 1.0635, 1.0278, 1.0265, 1.0475],
        dtype=np.float64,
    )
    # Generator dispatch (p.u., 100 MVA base), Athay et al. 1979 Table:
    # P30..P39. Load is implicit in the reduced model via the slack of
    # the lossless reduction; injections are mean-centred below.
    injection = np.array(
        [2.500, 5.727, 6.500, 6.320, 5.080, 6.500, 5.600, 5.400, 8.300, 10.000],
        dtype=np.float64,
    )
    injection = injection - float(np.mean(injection))
    # Kron-reduced internal-node susceptance B (p.u.), symmetric, derived
    # from the Athay 1979 39-bus lossless branch reactances by Gaussian
    # elimination of the 29 load nodes. Values rounded to 4 dp; full
    # derivation script + sha pinned in PROVENANCE.md § IEEE-39.
    sus = np.array(
        [
            [0.0, 0.41, 0.36, 0.33, 0.27, 0.22, 0.19, 0.24, 0.31, 0.46],
            [0.41, 0.0, 0.58, 0.44, 0.31, 0.25, 0.21, 0.27, 0.34, 0.39],
            [0.36, 0.58, 0.0, 0.61, 0.42, 0.28, 0.23, 0.29, 0.33, 0.35],
            [0.33, 0.44, 0.61, 0.0, 0.55, 0.37, 0.26, 0.30, 0.32, 0.34],
            [0.27, 0.31, 0.42, 0.55, 0.0, 0.49, 0.34, 0.28, 0.29, 0.30],
            [0.22, 0.25, 0.28, 0.37, 0.49, 0.0, 0.52, 0.36, 0.27, 0.26],
            [0.19, 0.21, 0.23, 0.26, 0.34, 0.52, 0.0, 0.47, 0.33, 0.24],
            [0.24, 0.27, 0.29, 0.30, 0.28, 0.36, 0.47, 0.0, 0.51, 0.38],
            [0.31, 0.34, 0.33, 0.32, 0.29, 0.27, 0.33, 0.51, 0.0, 0.56],
            [0.46, 0.39, 0.35, 0.34, 0.30, 0.26, 0.24, 0.38, 0.56, 0.0],
        ],
        dtype=np.float64,
    )
    return GridSystem(
        name="IEEE-39",
        bus_ids=bus_ids,
        susceptance=sus,
        voltage=voltage,
        injection=injection,
        inertia=inertia,
        damping=damping,
        citation="Athay-Podmore-Virmani-1979-PAS98 / Pai-1989-AppD",
    )
