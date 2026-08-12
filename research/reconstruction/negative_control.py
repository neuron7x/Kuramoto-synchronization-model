# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Negative-control null protocols for X-10R.

Cimini-Squartini reconstruction with IPF marginal projection recovers
EVERY informative-marginal input by construction — so any "null" that
preserves marginals will trivially pass Gate 5. The honest negative
control must therefore use ground-truth networks whose spectral
structure depends on TOPOLOGICAL features that the marginals alone
cannot encode. Three declared, finite null protocols:

  NEG_RING_LATTICE      regular 1-D ring with k=4 nearest neighbours,
                        unit weights. All marginals identical (constant
                        ≈ k · w_unit), so the fitness model collapses
                        to Erdős–Rényi(p). True ρ = 2k · w_unit comes
                        from the Toeplitz block structure; reconstructed
                        ρ comes from random-support gravity → Gate 5 ρ
                        check MUST fail.

  NEG_PATH_LATTICE      open 1-D chain (path). Each interior node has
                        identical strength 2·w_unit; endpoints have
                        w_unit. Even sparser than the ring → Cimini's
                        reconstructed ρ differs by orders of magnitude.

  NEG_2D_GRID           2-D square mesh (sqrt(N) × sqrt(N)). Every
                        interior node has identical 4-neighbour strength.
                        Lattice spectrum (cosine eigenvalues) is invisible
                        to a fitness model → Gate 5 ρ FAILS.

Contract: every negative-control substrate runs the SAME pipeline as
positive_control, then asserts ``passed == False`` (at least one density
in the sweep must fail Gate 5 to certify discriminativity). If ALL
densities of any null pass Gate 5, the instrument is BROKEN —
:class:`NegFalsePositiveError` is raised and no real-data verdict may
be emitted.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np

from research.reconstruction.positive_control import (
    _DENSITY_SWEEP,
    GroundTruthRecoveryCertificate,
    run_recovery_on_substrate,
)
from research.reconstruction.recovery_audit import RECOVERY_THRESHOLDS

# ---------------------------------------------------------------------------
# Null substrate generators
# ---------------------------------------------------------------------------


def neg_ring_lattice(n: int = 200, *, k: int = 4, w_unit: float = 1.0e5) -> np.ndarray:
    """Regular 1-D ring with k nearest neighbours, unit weights.

    Every node has identical strength → Cimini fitness collapses to
    Erdős–Rényi. True spectral structure (Toeplitz, ρ ≈ 2k·w_unit) is
    invisible to a fitness model.
    """
    if n < 2 * k + 4:
        raise ValueError(f"n must be ≥ 2k+4; got n={n}, k={k}")
    if w_unit <= 0:
        raise ValueError(f"w_unit must be > 0; got {w_unit}")
    w = np.zeros((n, n), dtype=np.float64)
    for i in range(n):
        for d in range(1, k + 1):
            j_fwd = (i + d) % n
            j_bwd = (i - d) % n
            w[i, j_fwd] = w_unit
            w[i, j_bwd] = w_unit
    np.fill_diagonal(w, 0.0)
    return w


def neg_path_lattice(n: int = 200, *, w_unit: float = 1.0e5) -> np.ndarray:
    """Open 1-D chain (path). Local linear topology, no fitness signal."""
    if n < 4:
        raise ValueError(f"n must be ≥ 4; got {n}")
    if w_unit <= 0:
        raise ValueError(f"w_unit must be > 0; got {w_unit}")
    w = np.zeros((n, n), dtype=np.float64)
    for i in range(n - 1):
        w[i, i + 1] = w_unit
        w[i + 1, i] = w_unit
    return w


def neg_2d_grid(n: int = 196, *, w_unit: float = 1.0e5) -> np.ndarray:
    """2-D square mesh; n must be a perfect square ≥ 16.

    Default n=196 = 14×14 (close to 200, mathematically clean).
    Each interior node has identical 4-neighbour strength; lattice
    eigenvalues come from a cosine spectrum that fitness can't see.
    """
    side = int(round(np.sqrt(n)))
    if side * side != n:
        raise ValueError(f"n must be a perfect square; got n={n} (sqrt={side})")
    if side < 4:
        raise ValueError(f"sqrt(n) must be ≥ 4; got {side}")
    if w_unit <= 0:
        raise ValueError(f"w_unit must be > 0; got {w_unit}")
    w = np.zeros((n, n), dtype=np.float64)
    for r in range(side):
        for c in range(side):
            i = r * side + c
            for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nr, nc = r + dr, c + dc
                if 0 <= nr < side and 0 <= nc < side:
                    j = nr * side + nc
                    w[i, j] = w_unit
    return w


# ---------------------------------------------------------------------------
# Negative-control aggregate certificate
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NegativeControlCertificate:
    null_name: str
    n_nodes: int
    sweep_densities: tuple[float, ...]
    per_density_passed: dict[float, bool]
    instrument_is_discriminative: bool  # True iff at least one density failed
    reason: str
    cert_id: str

    def is_valid(self) -> bool:
        return self.instrument_is_discriminative and bool(self.cert_id)


class NegFalsePositiveError(RuntimeError):
    """Raised when a null protocol unexpectedly PASSES Gate 5.

    Per Protocol X-10R: if any negative-control substrate is certified
    as 'recovered', the instrument has zero discriminative capacity
    and no real-data verdict may be emitted.
    """


def run_negative_control(
    null_name: str,
    w_null: np.ndarray,
    *,
    seed: int = 42,
    sweep: tuple[float, ...] = _DENSITY_SWEEP,
) -> NegativeControlCertificate:
    """Run reconstruction on a null substrate; certify discriminativity.

    Returns NegativeControlCertificate. If every density in the sweep
    PASSED Gate 5 on this null, raises NegFalsePositiveError — the
    instrument is broken.
    """
    pos_cert: GroundTruthRecoveryCertificate = run_recovery_on_substrate(
        substrate_name=f"NEG::{null_name}",
        w_true=w_null,
        seed=seed,
        sweep=sweep,
    )
    per_density_passed: dict[float, bool] = {
        d: report.passed for d, report in pos_cert.per_density_reports.items()
    }
    n_pass = sum(per_density_passed.values())
    n_total = len(per_density_passed)
    discriminative = n_pass < n_total  # at least one failure ⇒ instrument can say no
    if not discriminative and n_total > 0:
        raise NegFalsePositiveError(
            f"NEG_FALSE_POSITIVE: null protocol {null_name!r} passed Gate 5 on "
            f"every density in {sweep} — instrument has zero discriminative "
            f"capacity, real-data verdict FORBIDDEN."
        )
    cert_payload = (
        f"NEG|{null_name}|n={w_null.shape[0]}|seed={seed}|sweep={sweep}|"
        f"thresholds={sorted(RECOVERY_THRESHOLDS.items())}|"
        f"n_pass={n_pass}|n_total={n_total}"
    )
    cert_id = hashlib.sha256(cert_payload.encode("utf-8")).hexdigest()
    reason = f"{n_total - n_pass} of {n_total} densities failed Gate 5 — null correctly rejected"
    return NegativeControlCertificate(
        null_name=null_name,
        n_nodes=w_null.shape[0],
        sweep_densities=sweep,
        per_density_passed=per_density_passed,
        instrument_is_discriminative=discriminative,
        reason=reason,
        cert_id=cert_id,
    )


def run_all_negative_controls(
    *, n: int = 200, seed: int = 42
) -> dict[str, NegativeControlCertificate]:
    """Run the three declared null protocols; return cert per protocol.

    Raises NegFalsePositiveError if any null passes Gate 5 on every
    density in the sweep.
    """
    # n must be perfect square for the 2-D grid; default 196 ≈ 200.
    side = int(round(np.sqrt(n)))
    n_grid = side * side if side >= 4 else 196
    ring = neg_ring_lattice(n=n, k=4)
    path = neg_path_lattice(n=n)
    grid = neg_2d_grid(n=n_grid)
    return {
        "NEG_RING_LATTICE": run_negative_control("NEG_RING_LATTICE", ring, seed=seed + 11),
        "NEG_PATH_LATTICE": run_negative_control("NEG_PATH_LATTICE", path, seed=seed + 12),
        "NEG_2D_GRID": run_negative_control("NEG_2D_GRID", grid, seed=seed + 13),
    }
